#include <algorithm>
#include <chrono>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#include <Eigen/Geometry>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <moveit_msgs/msg/grasp.hpp>
#include <moveit_msgs/msg/gripper_translation.hpp>
#include <pcl/filters/crop_box.h>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl_conversions/pcl_conversions.h>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <so101_planner/srv/detect_grasps.hpp>
#include <tf2_eigen/tf2_eigen.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>

#include <gpd/candidate/hand.h>
#include <gpd/candidate/hand_set.h>
#include <gpd/grasp_detector.h>
#include <gpd/util/cloud.h>
#include <gpd/util/config_file.h>

using DetectGrasps = so101_planner::srv::DetectGrasps;
using PointXYZRGB = pcl::PointXYZRGB;
using PointCloud = pcl::PointCloud<PointXYZRGB>;

class GPDGraspDetectorNode : public rclcpp::Node
{
public:
  explicit GPDGraspDetectorNode(const rclcpp::NodeOptions& options)
    : rclcpp::Node("gpd_grasp_detector", options)
  {
    pointcloud_topic_ = declare_parameter<std::string>("pointcloud_topic", "/workspace/points");
    camera_frame_ = declare_parameter<std::string>("camera_frame", "camera_color_optical_frame");
    gpd_config_path_ = declare_parameter<std::string>("gpd_config_path", "package://so101_planner/config/gpd_cfg.yaml");
    grasp_score_threshold_ = declare_parameter<double>("grasp_score_threshold", 0.5);
    max_grasps_ = declare_parameter<int>("max_grasps", 40);
    pregrasp_distance_ = declare_parameter<double>("pregrasp_distance", 0.08);
    retreat_distance_ = declare_parameter<double>("retreat_distance", 0.10);
    crop_box_size_ = declare_parameter<std::vector<double>>("crop_box_size", { 0.25, 0.25, 0.20 });
    gripper_joint_names_ = declare_parameter<std::vector<std::string>>("gripper_joint_names", { "finger_joint" });
    gripper_open_positions_ = declare_parameter<std::vector<double>>("gripper_open_positions", { 0.04 });
    gripper_closed_positions_ = declare_parameter<std::vector<double>>("gripper_closed_positions", { 0.0 });

    gpd_config_path_ = resolveGpdConfigPath(gpd_config_path_);
    view_points_ = buildViewPoints(gpd_config_path_);
    grasp_detector_ = std::make_unique<gpd::GraspDetector>(gpd_config_path_);
    if (!grasp_detector_)
    {
      throw std::runtime_error("Failed to construct GPD grasp detector");
    }

    pointcloud_sub_ = create_subscription<sensor_msgs::msg::PointCloud2>(
        pointcloud_topic_, rclcpp::SensorDataQoS(),
        std::bind(&GPDGraspDetectorNode::pointcloudCallback, this, std::placeholders::_1));

    detect_service_ = create_service<DetectGrasps>(
        "detect_grasps",
        std::bind(&GPDGraspDetectorNode::handleDetectRequest, this, std::placeholders::_1, std::placeholders::_2));
  }

private:
  void pointcloudCallback(const sensor_msgs::msg::PointCloud2::SharedPtr msg)
  {
    std::lock_guard<std::mutex> lock(cloud_mutex_);
    latest_cloud_ = msg;
  }

  sensor_msgs::msg::PointCloud2::SharedPtr getLatestCloud() const
  {
    std::lock_guard<std::mutex> lock(cloud_mutex_);
    return latest_cloud_;
  }

  trajectory_msgs::msg::JointTrajectory buildPosture(const std::vector<double>& positions) const
  {
    trajectory_msgs::msg::JointTrajectory trajectory;
    trajectory.joint_names = gripper_joint_names_;
    trajectory.points.resize(1);
    trajectory.points.front().positions = positions;
    trajectory.points.front().time_from_start.sec = 0;
    trajectory.points.front().time_from_start.nanosec = 500000000;
    return trajectory;
  }

  moveit_msgs::msg::GripperTranslation buildTranslation(const Eigen::Vector3d& direction) const
  {
    moveit_msgs::msg::GripperTranslation translation;
    translation.direction.header.frame_id = camera_frame_;
    translation.direction.vector.x = direction.x();
    translation.direction.vector.y = direction.y();
    translation.direction.vector.z = direction.z();
    translation.min_distance = pregrasp_distance_ * 0.5;
    translation.desired_distance = pregrasp_distance_;
    return translation;
  }

  bool cropCloudAroundHint(const PointCloud::ConstPtr& input, const geometry_msgs::msg::PoseStamped& hint,
                           PointCloud::Ptr& output) const
  {
    if (hint.header.frame_id.empty() || hint.header.frame_id != input_frame_id_)
    {
      return false;
    }
    pcl::CropBox<PointXYZRGB> crop;
    const double half_x = crop_box_size_.size() > 0 ? crop_box_size_[0] * 0.5 : 0.2;
    const double half_y = crop_box_size_.size() > 1 ? crop_box_size_[1] * 0.5 : 0.2;
    const double half_z = crop_box_size_.size() > 2 ? crop_box_size_[2] * 0.5 : 0.2;
    Eigen::Vector4f min_pt(hint.pose.position.x - half_x, hint.pose.position.y - half_y,
                           hint.pose.position.z - half_z, 1.0f);
    Eigen::Vector4f max_pt(hint.pose.position.x + half_x, hint.pose.position.y + half_y,
                           hint.pose.position.z + half_z, 1.0f);
    crop.setMin(min_pt);
    crop.setMax(max_pt);
    crop.setInputCloud(input);
    crop.filter(*output);
    return true;
  }

  bool detectGrasps(const PointCloud::Ptr& cloud, std::vector<moveit_msgs::msg::Grasp>& grasps,
                    std::vector<float>& scores) const
  {
    if (!grasp_detector_)
    {
      RCLCPP_ERROR(get_logger(), "Grasp detector is not configured");
      return false;
    }
    pcl::PointCloud<pcl::PointXYZRGBA>::Ptr cloud_rgba(new pcl::PointCloud<pcl::PointXYZRGBA>);
    pcl::copyPointCloud(*cloud, *cloud_rgba);

    gpd::util::Cloud gpd_cloud(cloud_rgba, 0, view_points_);
    grasp_detector_->preprocessPointCloud(gpd_cloud);

    auto hands = grasp_detector_->detectGrasps(gpd_cloud);
    if (hands.empty())
    {
      return false;
    }

    grasps.clear();
    scores.clear();

    for (const auto& hand : hands)
    {
      if (!hand)
      {
        continue;
      }
      const double score = hand->getScore();
      if (score < grasp_score_threshold_)
      {
        continue;
      }
      moveit_msgs::msg::Grasp grasp_msg;
      grasp_msg.grasp_quality = score;
      grasp_msg.id = "gpd_grasp_" + std::to_string(grasps.size());

      Eigen::Isometry3d pose = Eigen::Isometry3d::Identity();
      pose.translation() = hand->getPosition();
      pose.linear().col(0) = hand->getApproach();
      pose.linear().col(1) = hand->getBinormal();
      pose.linear().col(2) = hand->getAxis();

      grasp_msg.grasp_pose.header.frame_id = camera_frame_;
      grasp_msg.grasp_pose.pose = tf2::toMsg(pose);

      grasp_msg.pre_grasp_posture = buildPosture(gripper_open_positions_);
      grasp_msg.grasp_posture = buildPosture(gripper_closed_positions_);

      grasp_msg.pre_grasp_approach = buildTranslation(hand->getApproach());
      Eigen::Vector3d retreat_vec = -hand->getApproach();
      grasp_msg.post_grasp_retreat = buildTranslation(retreat_vec);
      grasp_msg.post_grasp_retreat.min_distance = retreat_distance_;
      grasp_msg.post_grasp_retreat.desired_distance = retreat_distance_;
      grasp_msg.post_place_retreat = grasp_msg.post_grasp_retreat;

      grasps.emplace_back(grasp_msg);
      scores.emplace_back(static_cast<float>(score));
      if (max_grasps_ > 0 && static_cast<int>(grasps.size()) >= max_grasps_)
      {
        break;
      }
    }
    return !grasps.empty();
  }

  void handleDetectRequest(const std::shared_ptr<DetectGrasps::Request> request,
                           std::shared_ptr<DetectGrasps::Response> response)
  {
    auto cloud_msg = getLatestCloud();
    if (!cloud_msg)
    {
      response->success = false;
      response->message = "No point cloud received yet.";
      return;
    }

    PointCloud::Ptr cloud(new PointCloud);
    pcl::fromROSMsg(*cloud_msg, *cloud);
    input_frame_id_ = cloud_msg->header.frame_id;

    PointCloud::Ptr roi_cloud(new PointCloud);
    if (!cropCloudAroundHint(cloud, request->approximate_object_pose, roi_cloud) || roi_cloud->empty())
    {
      roi_cloud = cloud;
    }

    std::vector<moveit_msgs::msg::Grasp> grasps;
    std::vector<float> scores;
    if (!detectGrasps(roi_cloud, grasps, scores))
    {
      response->success = false;
      response->message = "GPD did not produce grasps.";
      return;
    }

    response->grasps = grasps;
    response->scores = scores;
    response->success = true;
    response->message = "Generated " + std::to_string(grasps.size()) + " grasps";
  }

  std::string resolveGpdConfigPath(const std::string& path) const
  {
    const std::string prefix = "package://";
    if (path.rfind(prefix, 0) != 0)
    {
      return path;
    }

    const auto remainder = path.substr(prefix.size());
    const auto slash_pos = remainder.find('/');
    if (slash_pos == std::string::npos)
    {
      RCLCPP_WARN(get_logger(), "Invalid GPD config URI: %s", path.c_str());
      return path;
    }

    const auto package_name = remainder.substr(0, slash_pos);
    const auto relative_path = remainder.substr(slash_pos + 1);
    try
    {
      const auto share_dir = ament_index_cpp::get_package_share_directory(package_name);
      return share_dir + "/" + relative_path;
    }
    catch (const std::exception& e)
    {
      RCLCPP_WARN(get_logger(), "Failed to resolve %s: %s", path.c_str(), e.what());
      return path;
    }
  }

  Eigen::Matrix3Xd buildViewPoints(const std::string& config_path) const
  {
    Eigen::Matrix3Xd view_points(3, 1);
    view_points << 0.0, 0.0, 0.0;
    try
    {
      gpd::util::ConfigFile config_file(config_path);
      config_file.ExtractKeys();
      const auto camera_position = config_file.getValueOfKeyAsStdVectorDouble("camera_position", "0.0 0.0 0.0");
      if (camera_position.size() >= 3)
      {
        view_points << camera_position[0], camera_position[1], camera_position[2];
      }
    }
    catch (const std::exception& e)
    {
      RCLCPP_WARN(get_logger(), "Failed to parse GPD config '%s': %s", config_path.c_str(), e.what());
    }
    return view_points;
  }

  std::string pointcloud_topic_;
  std::string camera_frame_;
  std::string gpd_config_path_;
  Eigen::Matrix3Xd view_points_;
  mutable std::mutex cloud_mutex_;
  sensor_msgs::msg::PointCloud2::SharedPtr latest_cloud_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr pointcloud_sub_;
  rclcpp::Service<DetectGrasps>::SharedPtr detect_service_;
  std::unique_ptr<gpd::GraspDetector> grasp_detector_;

  double grasp_score_threshold_{ 0.5 };
  int max_grasps_{ 40 };
  double pregrasp_distance_{ 0.08 };
  double retreat_distance_{ 0.10 };
  std::vector<double> crop_box_size_;
  std::vector<std::string> gripper_joint_names_;
  std::vector<double> gripper_open_positions_;
  std::vector<double> gripper_closed_positions_;
  std::string input_frame_id_;
};

int main(int argc, char** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions options;
  options.automatically_declare_parameters_from_overrides(false);
  auto node = std::make_shared<GPDGraspDetectorNode>(options);
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
