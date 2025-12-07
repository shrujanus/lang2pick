#ifndef SO101_PLANNER__SO101_PLANNER_HPP_
#define SO101_PLANNER__SO101_PLANNER_HPP_

#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/vector3.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit/task_constructor/stage.h>
#include <moveit/task_constructor/stages/compute_ik.h>
#include <moveit/task_constructor/task.h>
#include <moveit_msgs/msg/collision_object.hpp>
#include <octomap_msgs/msg/octomap.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rmw/types.h>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>

#include <so101_planner/srv/detect_grasps.hpp>
#include <so101_planner/srv/bounding_box_pick_place.hpp>
#include <so101_planner/srv/pick_place.hpp>

namespace mtc = moveit::task_constructor;

class GenerateGPDGrasps : public mtc::stages::ComputeIK
{
public:
  explicit GenerateGPDGrasps(const std::string& name = "generate gpd grasps");

  void setGrasps(const std::vector<moveit_msgs::msg::Grasp>& grasps, const std::vector<float>& scores);

private:
  class GPDPoseGenerator : public mtc::MonitoringGenerator
  {
  public:
    explicit GPDPoseGenerator(const std::string& name);

    void setGrasps(const std::vector<moveit_msgs::msg::Grasp>& grasps, const std::vector<float>& scores);
    void reset() override;

  protected:
    void onNewSolution(const mtc::SolutionBase& s) override;
    bool canCompute() const override;
    void compute() override;

  private:
    struct PendingSolution
    {
      const mtc::SolutionBase* solution;
      std::size_t next_index;
    };

    std::deque<PendingSolution> pending_;
    std::vector<moveit_msgs::msg::Grasp> grasps_;
    std::vector<float> scores_;
    std::vector<std::size_t> ordered_indices_;
  };

  GPDPoseGenerator* generator_{ nullptr };
};

class So101Planner
{
public:
  explicit So101Planner(const rclcpp::NodeOptions& options);

  rclcpp::node_interfaces::NodeBaseInterface::SharedPtr getNodeBaseInterface();

private:
  void loadParameters();
  bool doTask(const std::vector<moveit_msgs::msg::Grasp>& grasps, const std::vector<float>& scores);
  mtc::Task createTask(const std::vector<moveit_msgs::msg::Grasp>& grasps, const std::vector<float>& scores);
  bool transformPoseToWorld(const geometry_msgs::msg::PoseStamped& input, geometry_msgs::msg::PoseStamped& output);
  bool waitForCollisionObject(const std::string& object_id, const rclcpp::Duration& timeout);
  bool requestGraspsFromGPD(const geometry_msgs::msg::PoseStamped& approximate_pose,
                            std::vector<moveit_msgs::msg::Grasp>& grasps, std::vector<float>& scores);
  bool extractObjectFromBoundingBox(const std::vector<float>& bbox_pixels, geometry_msgs::msg::PoseStamped& pose,
                                    geometry_msgs::msg::Vector3& dimensions);
  bool applyCollisionObjectFromBoundingBox(const geometry_msgs::msg::PoseStamped& pose,
                                           const geometry_msgs::msg::Vector3& dimensions);
  void rgbdPointCloudCallback(const sensor_msgs::msg::PointCloud2::SharedPtr msg);

  void octomapCallback(const octomap_msgs::msg::Octomap::SharedPtr msg);
  void handlePickPlaceRequest(const std::shared_ptr<rmw_request_id_t> request_header,
                              const std::shared_ptr<::so101_planner::srv::PickPlace::Request> request,
                              std::shared_ptr<::so101_planner::srv::PickPlace::Response> response);
  void
  handleBoundingBoxPickPlaceRequest(const std::shared_ptr<rmw_request_id_t> request_header,
                                    const std::shared_ptr<::so101_planner::srv::BoundingBoxPickPlace::Request> request,
                                    std::shared_ptr<::so101_planner::srv::BoundingBoxPickPlace::Response> response);

  mtc::Task task_;
  rclcpp::Node::SharedPtr node_;
  std::shared_ptr<tf2_ros::Buffer> tf_buffer_;
  std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
  rclcpp::Service<::so101_planner::srv::PickPlace>::SharedPtr pick_place_service_;
  rclcpp::Service<::so101_planner::srv::BoundingBoxPickPlace>::SharedPtr bbox_pick_place_service_;
  rclcpp::Subscription<octomap_msgs::msg::Octomap>::SharedPtr octomap_sub_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr rgbd_cloud_sub_;
  rclcpp::Client<::so101_planner::srv::DetectGrasps>::SharedPtr gpd_client_;
  moveit::planning_interface::PlanningSceneInterface planning_scene_interface_;

  geometry_msgs::msg::PoseStamped pick_pose_;
  geometry_msgs::msg::PoseStamped place_pose_;
  geometry_msgs::msg::PoseStamped ik_frame_pose_;

  std::string object_id_ = "object";
  std::string arm_group_name_ = "so101_arm";
  std::string gripper_group_name_ = "gripper";
  std::string gripper_open_pose_ = "gripper_open";
  std::string gripper_close_pose_ = "gripper_close";
  std::string home_pose_name_ = "init";
  std::string octomap_topic_ = "/octomap_binary";
  std::string gpd_service_name_ = "/detect_grasps";
  std::string rgbd_pointcloud_topic_ = "/camera/depth_registered/points";

  double approach_min_distance_ = 0.05;
  double approach_max_distance_ = 0.15;
  double lift_distance_ = 0.12;
  double retreat_distance_ = 0.18;
  double object_wait_timeout_sec_ = 10.0;
  double grasp_service_timeout_sec_ = 10.0;
  int planning_attempts_ = 10;

  std::mutex task_mutex_;
  std::mutex rgbd_cloud_mutex_;
  sensor_msgs::msg::PointCloud2::SharedPtr latest_rgbd_cloud_;
  rclcpp::Time last_octomap_update_;

  inline static constexpr const char* kWorldFrame = "world";
  inline static constexpr const char* kBaseLink = "base_link";
  inline static constexpr const char* kHandFrame = "gripper_frame_link";
  inline static constexpr const char* kGripperBodyLink = "gripper_link";
  inline static constexpr const char* kJawLink = "moving_jaw_so101_v1_link";
};

#endif  // SO101_PLANNER__SO101_PLANNER_HPP_
