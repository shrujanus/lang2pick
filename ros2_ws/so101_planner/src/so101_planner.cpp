#include <so101_planner/so101_planner.hpp>

#include <Eigen/Core>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <future>
#include <numeric>

#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <moveit/planning_scene/planning_scene.h>
#include <moveit/task_constructor/solvers/cartesian_path.h>
#include <moveit/task_constructor/solvers/joint_interpolation.h>
#include <moveit/task_constructor/solvers/pipeline_planner.h>
#include <moveit/task_constructor/stages/connect.h>
#include <moveit/task_constructor/stages/current_state.h>
#include <moveit/task_constructor/stages/generate_place_pose.h>
#include <moveit/task_constructor/stages/modify_planning_scene.h>
#include <moveit/task_constructor/stages/move_relative.h>
#include <moveit/task_constructor/stages/move_to.h>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <moveit_msgs/msg/planning_scene.hpp>
#include <octomap_msgs/msg/octomap.hpp>
#include <rclcpp/executors/multi_threaded_executor.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/exceptions.h>
#if __has_include(<tf2_geometry_msgs/tf2_geometry_msgs.hpp>)
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#else
#include <tf2_geometry_msgs/tf2_geometry_msgs.h>
#endif
#if __has_include(<tf2_eigen/tf2_eigen.hpp>)
#include <tf2_eigen/tf2_eigen.hpp>
#else
#include <tf2_eigen/tf2_eigen.h>
#endif

using namespace std::chrono_literals;

namespace
{
geometry_msgs::msg::Quaternion createQuaternionFromRPY(double roll, double pitch, double yaw)
{
  tf2::Quaternion q;
  q.setRPY(roll, pitch, yaw);
  q.normalize();
  geometry_msgs::msg::Quaternion msg;
  msg = tf2::toMsg(q);
  return msg;
}
}  // namespace

static const rclcpp::Logger LOGGER = rclcpp::get_logger("so101_planner");

// -- GenerateGPDGrasps -------------------------------------------------------

GenerateGPDGrasps::GPDPoseGenerator::GPDPoseGenerator(const std::string& name) : mtc::MonitoringGenerator(name)
{
  auto& props = properties();
  props.declare<std::string>("marker_ns", "rviz marker namespace");
}

void GenerateGPDGrasps::GPDPoseGenerator::setGrasps(const std::vector<moveit_msgs::msg::Grasp>& grasps,
                                                    const std::vector<float>& scores)
{
  grasps_ = grasps;
  scores_ = scores;
  ordered_indices_.clear();
  ordered_indices_.resize(grasps_.size());
  std::iota(ordered_indices_.begin(), ordered_indices_.end(), 0u);
  std::sort(ordered_indices_.begin(), ordered_indices_.end(), [&](std::size_t lhs, std::size_t rhs) {
    const double lhs_score = lhs < scores_.size() ? scores_[lhs] : 0.0;
    const double rhs_score = rhs < scores_.size() ? scores_[rhs] : 0.0;
    return lhs_score > rhs_score;
  });
}

void GenerateGPDGrasps::GPDPoseGenerator::reset()
{
  pending_.clear();
  mtc::MonitoringGenerator::reset();
}

void GenerateGPDGrasps::GPDPoseGenerator::onNewSolution(const mtc::SolutionBase& solution)
{
  pending_.push_back({ &solution, 0u });
}

bool GenerateGPDGrasps::GPDPoseGenerator::canCompute() const
{
  return !pending_.empty() && !ordered_indices_.empty();
}

void GenerateGPDGrasps::GPDPoseGenerator::compute()
{
  if (pending_.empty() || ordered_indices_.empty())
  {
    return;
  }

  auto active = pending_.front();
  pending_.pop_front();

  if (active.next_index >= ordered_indices_.size())
  {
    return;
  }

  const std::size_t ordered_index = ordered_indices_.at(active.next_index);
  ++active.next_index;
  if (active.next_index < ordered_indices_.size())
  {
    pending_.push_back(active);
  }

  const auto& upstream_solution = *active.solution;
  planning_scene::PlanningSceneConstPtr scene = upstream_solution.end()->scene()->diff();
  const auto& grasp = grasps_.at(ordered_index);

  geometry_msgs::msg::PoseStamped target_pose = grasp.grasp_pose;
  if (target_pose.header.frame_id.empty())
  {
    target_pose.header.frame_id = scene->getPlanningFrame();
  }

  mtc::InterfaceState state(scene);
  forwardProperties(*upstream_solution.end(), state);
  state.properties().set("target_pose", target_pose);
  state.properties().set("grasp", grasp);

  mtc::SubTrajectory trajectory;
  const double score = ordered_index < scores_.size() ? static_cast<double>(scores_[ordered_index]) : 0.0;
  trajectory.setCost(1.0 - std::clamp(score, 0.0, 1.0));

  spawn(std::move(state), std::move(trajectory));
}

GenerateGPDGrasps::GenerateGPDGrasps(const std::string& name)
  : mtc::stages::ComputeIK(name, mtc::Stage::pointer(new GPDPoseGenerator(name + "_pose_generator")))
{
  generator_ = dynamic_cast<GPDPoseGenerator*>(wrapped());
}

void GenerateGPDGrasps::setGrasps(const std::vector<moveit_msgs::msg::Grasp>& grasps, const std::vector<float>& scores)
{
  if (generator_ == nullptr)
  {
    RCLCPP_ERROR(LOGGER, "GPD pose generator is not ready");
    return;
  }
  generator_->setGrasps(grasps, scores);
}

// -- So101Planner ------------------------------------------------------------

rclcpp::node_interfaces::NodeBaseInterface::SharedPtr So101Planner::getNodeBaseInterface()
{
  return node_->get_node_base_interface();
}

So101Planner::So101Planner(const rclcpp::NodeOptions& options)
  : node_{ std::make_shared<rclcpp::Node>("so101_planner", options) }, last_octomap_update_{ node_->now() }
{
  using std::placeholders::_1;
  using std::placeholders::_2;
  using std::placeholders::_3;

  loadParameters();

  tf_buffer_ = std::make_shared<tf2_ros::Buffer>(node_->get_clock());
  tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_, node_, false);

  gpd_client_ = node_->create_client<::so101_planner::srv::DetectGrasps>(gpd_service_name_);
  octomap_sub_ = node_->create_subscription<octomap_msgs::msg::Octomap>(
      octomap_topic_, rclcpp::QoS(1).best_effort(), std::bind(&So101Planner::octomapCallback, this, _1));
  rgbd_cloud_sub_ = node_->create_subscription<sensor_msgs::msg::PointCloud2>(
      rgbd_pointcloud_topic_, rclcpp::SensorDataQoS(), std::bind(&So101Planner::rgbdPointCloudCallback, this, _1));

  pick_place_service_ = node_->create_service<::so101_planner::srv::PickPlace>(
      "pick_place", std::bind(&So101Planner::handlePickPlaceRequest, this, _1, _2, _3));
  bbox_pick_place_service_ = node_->create_service<::so101_planner::srv::BoundingBoxPickPlace>(
      "pick_place_from_bbox", std::bind(&So101Planner::handleBoundingBoxPickPlaceRequest, this, _1, _2, _3));
}

void So101Planner::loadParameters()
{
  auto get_param = [this](const std::string& name, auto default_value) {
    using ParamType = std::decay_t<decltype(default_value)>;
    if (!node_->has_parameter(name))
    {
      node_->declare_parameter<ParamType>(name, default_value);
    }
    ParamType value{};
    node_->get_parameter(name, value);
    return value;
  };

  arm_group_name_ = get_param("arm_group_name", arm_group_name_);
  gripper_group_name_ = get_param("gripper_group_name", gripper_group_name_);
  gripper_open_pose_ = get_param("gripper_open_pose", gripper_open_pose_);
  gripper_close_pose_ = get_param("gripper_close_pose", gripper_close_pose_);
  home_pose_name_ = get_param("home_pose_name", home_pose_name_);
  octomap_topic_ = get_param("octomap_topic", octomap_topic_);
  gpd_service_name_ = get_param("gpd_service_name", gpd_service_name_);
  rgbd_pointcloud_topic_ = get_param("rgbd_pointcloud_topic", rgbd_pointcloud_topic_);
  planning_attempts_ = get_param("planning_attempts", planning_attempts_);
  approach_min_distance_ = get_param("approach_min_distance", approach_min_distance_);
  approach_max_distance_ = get_param("approach_max_distance", approach_max_distance_);
  lift_distance_ = get_param("lift_distance", lift_distance_);
  retreat_distance_ = get_param("retreat_distance", retreat_distance_);
  object_wait_timeout_sec_ = get_param("object_wait_timeout", object_wait_timeout_sec_);
  grasp_service_timeout_sec_ = get_param("grasp_service_timeout", grasp_service_timeout_sec_);

  const std::string ik_frame_link = get_param("ik_frame_link", std::string(kGripperBodyLink));
  const std::vector<double> ik_frame_translation =
      get_param("ik_frame_translation", std::vector<double>{ 0.0, 0.0, 0.0 });
  const std::vector<double> ik_frame_rpy = get_param("ik_frame_rpy", std::vector<double>{ 0.0, 0.0, 0.0 });

  ik_frame_pose_.header.frame_id = ik_frame_link;
  if (ik_frame_translation.size() == 3U)
  {
    ik_frame_pose_.pose.position.x = ik_frame_translation[0];
    ik_frame_pose_.pose.position.y = ik_frame_translation[1];
    ik_frame_pose_.pose.position.z = ik_frame_translation[2];
  }
  ik_frame_pose_.pose.orientation = createQuaternionFromRPY(ik_frame_rpy.size() > 0 ? ik_frame_rpy[0] : 0.0,
                                                            ik_frame_rpy.size() > 1 ? ik_frame_rpy[1] : 0.0,
                                                            ik_frame_rpy.size() > 2 ? ik_frame_rpy[2] : 0.0);
}

bool So101Planner::transformPoseToWorld(const geometry_msgs::msg::PoseStamped& input,
                                        geometry_msgs::msg::PoseStamped& output)
{
  output = input;
  if (output.header.frame_id.empty())
  {
    output.header.frame_id = kWorldFrame;
  }
  if (output.pose.orientation.w == 0.0 && output.pose.orientation.x == 0.0 && output.pose.orientation.y == 0.0 &&
      output.pose.orientation.z == 0.0)
  {
    output.pose.orientation.w = 1.0;
  }

  if (output.header.frame_id == kWorldFrame)
  {
    return true;
  }

  if (!tf_buffer_)
  {
    RCLCPP_ERROR(LOGGER, "TF buffer is not available");
    return false;
  }

  try
  {
    const auto timeout = rclcpp::Duration::from_seconds(2.0);
    const auto transform = tf_buffer_->lookupTransform(kWorldFrame, output.header.frame_id, rclcpp::Time(0), timeout);
    tf2::doTransform(input, output, transform);
    output.header.frame_id = kWorldFrame;
    return true;
  }
  catch (const tf2::TransformException& ex)
  {
    RCLCPP_ERROR(LOGGER, "Failed to transform pose from '%s' to '%s': %s", input.header.frame_id.c_str(), kWorldFrame,
                 ex.what());
    return false;
  }
}

void So101Planner::octomapCallback(const octomap_msgs::msg::Octomap::SharedPtr msg)
{
  moveit_msgs::msg::PlanningScene scene_msg;
  scene_msg.is_diff = true;
  scene_msg.world.octomap.header = msg->header;
  scene_msg.world.octomap.octomap = *msg;
  planning_scene_interface_.applyPlanningScene(scene_msg);
  last_octomap_update_ = node_->now();
}

bool So101Planner::waitForCollisionObject(const std::string& object_id, const rclcpp::Duration& timeout)
{
  const rclcpp::Time start_time = node_->now();
  rclcpp::Rate rate(10.0);
  while (rclcpp::ok() && (node_->now() - start_time) < timeout)
  {
    auto objects = planning_scene_interface_.getObjects({ object_id });
    if (!objects.empty())
    {
      return true;
    }
    rate.sleep();
  }
  return false;
}

bool So101Planner::requestGraspsFromGPD(const geometry_msgs::msg::PoseStamped& approximate_pose,
                                        std::vector<moveit_msgs::msg::Grasp>& grasps, std::vector<float>& scores)
{
  if (!gpd_client_)
  {
    RCLCPP_ERROR(LOGGER, "GPD service client is not initialized");
    return false;
  }

  if (!gpd_client_->wait_for_service(5s))
  {
    RCLCPP_ERROR(LOGGER, "GPD service '%s' is not available", gpd_service_name_.c_str());
    return false;
  }

  auto request = std::make_shared<::so101_planner::srv::DetectGrasps::Request>();
  request->approximate_object_pose = approximate_pose;

  auto future = gpd_client_->async_send_request(request);
  const auto wait_status = future.wait_for(std::chrono::duration<double>(grasp_service_timeout_sec_));
  if (wait_status != std::future_status::ready)
  {
    RCLCPP_ERROR(LOGGER, "Timed out waiting for GPD response");
    return false;
  }

  const auto response = future.get();
  if (!response->success || response->grasps.empty())
  {
    RCLCPP_WARN(LOGGER, "GPD did not return any grasps: %s", response->message.c_str());
    return false;
  }

  grasps = response->grasps;
  scores = response->scores;
  if (scores.size() != grasps.size())
  {
    scores.resize(grasps.size(), 1.0f);
  }
  return true;
}

void So101Planner::rgbdPointCloudCallback(const sensor_msgs::msg::PointCloud2::SharedPtr msg)
{
  std::lock_guard<std::mutex> lock(rgbd_cloud_mutex_);
  latest_rgbd_cloud_ = msg;
}

bool So101Planner::extractObjectFromBoundingBox(const std::vector<float>& bbox_pixels,
                                                geometry_msgs::msg::PoseStamped& pose,
                                                geometry_msgs::msg::Vector3& dimensions)
{
  if (bbox_pixels.size() != 8)
  {
    RCLCPP_ERROR(LOGGER, "Bounding box requires 4 (x,y) pairs");
    return false;
  }

  sensor_msgs::msg::PointCloud2::SharedPtr cloud;
  {
    std::lock_guard<std::mutex> lock(rgbd_cloud_mutex_);
    cloud = latest_rgbd_cloud_;
  }
  if (!cloud)
  {
    RCLCPP_ERROR(LOGGER, "No RGB-D point cloud available for bounding box projection");
    return false;
  }

  if (cloud->width == 0 || cloud->height <= 1)
  {
    RCLCPP_ERROR(LOGGER, "RGB-D point cloud must be organized");
    return false;
  }

  const int width = static_cast<int>(cloud->width);
  const int height = static_cast<int>(cloud->height);
  int min_u = width - 1;
  int max_u = 0;
  int min_v = height - 1;
  int max_v = 0;

  for (std::size_t i = 0; i < 4; ++i)
  {
    int u = static_cast<int>(std::lround(bbox_pixels[2 * i + 0]));
    int v = static_cast<int>(std::lround(bbox_pixels[2 * i + 1]));
    u = std::clamp(u, 0, width - 1);
    v = std::clamp(v, 0, height - 1);
    min_u = std::min(min_u, u);
    max_u = std::max(max_u, u);
    min_v = std::min(min_v, v);
    max_v = std::max(max_v, v);
  }

  if (min_u > max_u || min_v > max_v)
  {
    RCLCPP_ERROR(LOGGER, "Invalid bounding box pixel range");
    return false;
  }

  int offset_x = -1;
  int offset_y = -1;
  int offset_z = -1;
  for (const auto& field : cloud->fields)
  {
    if (field.name == "x")
      offset_x = field.offset;
    else if (field.name == "y")
      offset_y = field.offset;
    else if (field.name == "z")
      offset_z = field.offset;
  }
  if (offset_x < 0 || offset_y < 0 || offset_z < 0)
  {
    RCLCPP_ERROR(LOGGER, "Point cloud missing XYZ fields");
    return false;
  }

  const auto point_step = static_cast<std::size_t>(cloud->point_step);
  const auto row_step = static_cast<std::size_t>(cloud->row_step);
  const auto& data = cloud->data;

  bool initialized = false;
  Eigen::Vector3d min_point;
  Eigen::Vector3d max_point;

  const int max_offset = std::max(offset_x, std::max(offset_y, offset_z));

  for (int v = min_v; v <= max_v; ++v)
  {
    const std::size_t row_offset = static_cast<std::size_t>(v) * row_step;
    for (int u = min_u; u <= max_u; ++u)
    {
      const std::size_t index = row_offset + static_cast<std::size_t>(u) * point_step;
      if (index + static_cast<std::size_t>(max_offset) + sizeof(float) > data.size())
      {
        continue;
      }
      const float x = *reinterpret_cast<const float*>(&data[index + offset_x]);
      const float y = *reinterpret_cast<const float*>(&data[index + offset_y]);
      const float z = *reinterpret_cast<const float*>(&data[index + offset_z]);
      if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z))
      {
        continue;
      }
      const Eigen::Vector3d point(x, y, z);
      if (!initialized)
      {
        min_point = point;
        max_point = point;
        initialized = true;
      }
      else
      {
        min_point = min_point.cwiseMin(point);
        max_point = max_point.cwiseMax(point);
      }
    }
  }

  if (!initialized)
  {
    RCLCPP_ERROR(LOGGER, "Bounding box area contains no valid depth points");
    return false;
  }

  const Eigen::Vector3d center = 0.5 * (min_point + max_point);
  const Eigen::Vector3d extents = (max_point - min_point).cwiseAbs();

  geometry_msgs::msg::PoseStamped camera_pose;
  camera_pose.header = cloud->header;
  camera_pose.pose.position.x = center.x();
  camera_pose.pose.position.y = center.y();
  camera_pose.pose.position.z = center.z();
  camera_pose.pose.orientation.w = 1.0;
  camera_pose.pose.orientation.x = camera_pose.pose.orientation.y = camera_pose.pose.orientation.z = 0.0;

  if (!transformPoseToWorld(camera_pose, pose))
  {
    RCLCPP_ERROR(LOGGER, "Failed to transform bounding box pose to world frame");
    return false;
  }

  dimensions.x = std::max(extents.x(), 0.01);
  dimensions.y = std::max(extents.y(), 0.01);
  dimensions.z = std::max(extents.z(), 0.01);
  return true;
}

bool So101Planner::applyCollisionObjectFromBoundingBox(const geometry_msgs::msg::PoseStamped& pose,
                                                       const geometry_msgs::msg::Vector3& dimensions)
{
  moveit_msgs::msg::CollisionObject collision;
  collision.id = object_id_;
  collision.header = pose.header;
  collision.pose = pose.pose;
  collision.primitives.resize(1);
  collision.primitives[0].type = shape_msgs::msg::SolidPrimitive::BOX;
  collision.primitives[0].dimensions = { dimensions.x, dimensions.y, dimensions.z };

  planning_scene_interface_.removeCollisionObjects({ object_id_ });
  planning_scene_interface_.applyCollisionObject(collision);
  return true;
}

void So101Planner::handlePickPlaceRequest(const std::shared_ptr<rmw_request_id_t> /*request_header*/,
                                          const std::shared_ptr<::so101_planner::srv::PickPlace::Request> request,
                                          std::shared_ptr<::so101_planner::srv::PickPlace::Response> response)
{
  std::lock_guard<std::mutex> lock(task_mutex_);
  object_id_ = request->object_id.empty() ? "object" : request->object_id;

  if (!transformPoseToWorld(request->pick_pose, pick_pose_))
  {
    response->success = false;
    response->message = "Failed to transform pick pose to world frame.";
    return;
  }
  if (!transformPoseToWorld(request->place_pose, place_pose_))
  {
    response->success = false;
    response->message = "Failed to transform place pose to world frame.";
    return;
  }

  RCLCPP_INFO(LOGGER, "Waiting for object '%s' in planning scene", object_id_.c_str());
  if (!waitForCollisionObject(object_id_, rclcpp::Duration::from_seconds(object_wait_timeout_sec_)))
  {
    response->success = false;
    response->message = "Object never appeared in planning scene.";
    return;
  }

  std::vector<moveit_msgs::msg::Grasp> grasps;
  std::vector<float> scores;
  if (!requestGraspsFromGPD(pick_pose_, grasps, scores))
  {
    response->success = false;
    response->message = "Failed to retrieve grasps from GPD.";
    return;
  }

  const bool success = doTask(grasps, scores);
  response->success = success;
  response->message = success ? "Perception-driven pick and place completed." : "Pick and place failed.";
}

void So101Planner::handleBoundingBoxPickPlaceRequest(
    const std::shared_ptr<rmw_request_id_t> /*request_header*/,
    const std::shared_ptr<::so101_planner::srv::BoundingBoxPickPlace::Request> request,
    std::shared_ptr<::so101_planner::srv::BoundingBoxPickPlace::Response> response)
{
  std::lock_guard<std::mutex> lock(task_mutex_);
  object_id_ = request->object_id.empty() ? "object" : request->object_id;

  if (!transformPoseToWorld(request->place_pose, place_pose_))
  {
    response->success = false;
    response->message = "Failed to transform place pose to world frame.";
    return;
  }

  geometry_msgs::msg::PoseStamped object_pose_world;
  geometry_msgs::msg::Vector3 object_dimensions;
  if (!extractObjectFromBoundingBox(request->bbox_pixels, object_pose_world, object_dimensions))
  {
    response->success = false;
    response->message = "Failed to compute bounding box pose from depth data.";
    return;
  }

  if (!applyCollisionObjectFromBoundingBox(object_pose_world, object_dimensions))
  {
    response->success = false;
    response->message = "Failed to update planning scene with bounding box object.";
    return;
  }

  pick_pose_ = object_pose_world;
  pick_pose_.pose.position.z += std::max(object_dimensions.z * 0.5, 0.01);
  if (pick_pose_.pose.orientation.w == 0.0 && pick_pose_.pose.orientation.x == 0.0 &&
      pick_pose_.pose.orientation.y == 0.0 && pick_pose_.pose.orientation.z == 0.0)
  {
    pick_pose_.pose.orientation.w = 1.0;
  }

  std::vector<moveit_msgs::msg::Grasp> grasps;
  std::vector<float> scores;
  if (!requestGraspsFromGPD(pick_pose_, grasps, scores))
  {
    response->success = false;
    response->message = "Failed to retrieve grasps from GPD.";
    return;
  }

  const bool success = doTask(grasps, scores);
  response->success = success;
  response->message = success ? "Bounding box pick and place completed." : "Pick and place failed.";
}

bool So101Planner::doTask(const std::vector<moveit_msgs::msg::Grasp>& grasps, const std::vector<float>& scores)
{
  task_ = createTask(grasps, scores);

  try
  {
    task_.init();
  }
  catch (mtc::InitStageException& e)
  {
    RCLCPP_ERROR_STREAM(LOGGER, e);
    return false;
  }

  if (!task_.plan(planning_attempts_))
  {
    RCLCPP_ERROR(LOGGER, "Task planning failed");
    return false;
  }

  if (task_.solutions().empty())
  {
    RCLCPP_ERROR(LOGGER, "No task solutions found");
    return false;
  }

  auto& first_solution = *task_.solutions().front();
  task_.introspection().publishSolution(first_solution);

  const auto result = task_.execute(first_solution);
  if (result.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS)
  {
    RCLCPP_ERROR(LOGGER, "Task execution returned error code %d", result.val);
    return false;
  }

  return true;
}

mtc::Task So101Planner::createTask(const std::vector<moveit_msgs::msg::Grasp>& grasps, const std::vector<float>& scores)
{
  mtc::Task task;
  task.stages()->setName("so101 perception pick and place");
  task.loadRobotModel(node_);

  task.setProperty("group", arm_group_name_);
  task.setProperty("eef", gripper_group_name_);
  task.setProperty("object", object_id_);
  task.setProperty("ik_frame", ik_frame_pose_);
  task.setProperty("global_frame", kWorldFrame);

  mtc::Stage* current_state_ptr = nullptr;
  auto current_state = std::make_unique<mtc::stages::CurrentState>("current state");
  current_state_ptr = current_state.get();
  task.add(std::move(current_state));

  auto sampling_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node_);
  auto interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
  auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
  cartesian_planner->setMaxVelocityScalingFactor(1.0);
  cartesian_planner->setMaxAccelerationScalingFactor(1.0);
  cartesian_planner->setStepSize(0.005);

  auto open_hand = std::make_unique<mtc::stages::MoveTo>("open hand", interpolation_planner);
  open_hand->setGroup(gripper_group_name_);
  open_hand->setGoal(gripper_open_pose_);
  task.add(std::move(open_hand));

  auto move_to_pick = std::make_unique<mtc::stages::Connect>(
      "move to pick area", mtc::stages::Connect::GroupPlannerVector{ { arm_group_name_, sampling_planner } });
  move_to_pick->properties().configureInitFrom(mtc::Stage::PARENT);
  move_to_pick->setTimeout(5.0);
  task.add(std::move(move_to_pick));

  auto gpd_stage = std::make_unique<GenerateGPDGrasps>("generate gpd grasps");
  gpd_stage->properties().configureInitFrom(mtc::Stage::PARENT);
  gpd_stage->setGrasps(grasps, scores);
  gpd_stage->setGroup(arm_group_name_);
  gpd_stage->setEndEffector(gripper_group_name_);
  gpd_stage->setIKFrame(ik_frame_pose_);
  gpd_stage->setMaxIKSolutions(16);
  gpd_stage->setMinSolutionDistance(0.05);
  task.add(std::move(gpd_stage));

  auto approach = std::make_unique<mtc::stages::MoveRelative>("approach object", cartesian_planner);
  approach->properties().configureInitFrom(mtc::Stage::PARENT);
  approach->setGroup(arm_group_name_);
  geometry_msgs::msg::Vector3Stamped approach_direction;
  approach_direction.header.frame_id = kHandFrame;
  approach_direction.vector.z = -1.0;
  approach->setDirection(approach_direction);
  approach->setMinMaxDistance(approach_min_distance_, approach_max_distance_);
  task.add(std::move(approach));

  auto allow_collision = std::make_unique<mtc::stages::ModifyPlanningScene>("allow grasp collision");
  allow_collision->allowCollisions(object_id_, kGripperBodyLink, true);
  allow_collision->allowCollisions(object_id_, kHandFrame, true);
  allow_collision->allowCollisions(object_id_, kJawLink, true);
  task.add(std::move(allow_collision));

  auto close_hand = std::make_unique<mtc::stages::MoveTo>("close hand", interpolation_planner);
  close_hand->setGroup(gripper_group_name_);
  close_hand->setGoal(gripper_close_pose_);
  task.add(std::move(close_hand));

  mtc::Stage* attach_object_stage = nullptr;
  auto attach_object = std::make_unique<mtc::stages::ModifyPlanningScene>("attach object");
  attach_object->attachObject(object_id_, kHandFrame);
  attach_object_stage = attach_object.get();
  task.add(std::move(attach_object));

  auto lift = std::make_unique<mtc::stages::MoveRelative>("lift object", cartesian_planner);
  lift->properties().configureInitFrom(mtc::Stage::PARENT);
  lift->setGroup(arm_group_name_);
  geometry_msgs::msg::Vector3Stamped lift_direction;
  lift_direction.header.frame_id = kBaseLink;
  lift_direction.vector.z = 1.0;
  lift->setDirection(lift_direction);
  lift->setMinMaxDistance(0.02, lift_distance_);
  task.add(std::move(lift));

  auto move_to_place = std::make_unique<mtc::stages::Connect>(
      "move to place area", mtc::stages::Connect::GroupPlannerVector{ { arm_group_name_, sampling_planner } });
  move_to_place->properties().configureInitFrom(mtc::Stage::PARENT);
  move_to_place->setTimeout(5.0);
  task.add(std::move(move_to_place));

  auto place_container = std::make_unique<mtc::SerialContainer>("place object");
  task.properties().exposeTo(place_container->properties(), { "group", "eef", "ik_frame", "object" });
  place_container->properties().configureInitFrom(mtc::Stage::PARENT, { "group", "eef", "ik_frame", "object" });

  geometry_msgs::msg::PoseStamped place_pose = place_pose_;
  if (place_pose.header.frame_id.empty())
  {
    place_pose.header.frame_id = kWorldFrame;
  }
  if (place_pose.pose.orientation.w == 0.0 && place_pose.pose.orientation.x == 0.0 &&
      place_pose.pose.orientation.y == 0.0 && place_pose.pose.orientation.z == 0.0)
  {
    place_pose.pose.orientation.w = 1.0;
  }

  {
    auto generate_place = std::make_unique<mtc::stages::GeneratePlacePose>("generate place pose");
    generate_place->properties().configureInitFrom(mtc::Stage::PARENT);
    generate_place->properties().set("marker_ns", "place_pose");
    generate_place->properties().set("object", object_id_);
    generate_place->setMonitoredStage(attach_object_stage);
    generate_place->setPose(place_pose);

    auto compute_place = std::make_unique<mtc::stages::ComputeIK>("compute place IK", std::move(generate_place));
    compute_place->properties().configureInitFrom(mtc::Stage::PARENT, { "group", "eef", "ik_frame" });
    compute_place->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
    compute_place->setMaxIKSolutions(8);
    compute_place->setMinSolutionDistance(0.05);
    compute_place->setIKFrame(ik_frame_pose_);
    place_container->add(std::move(compute_place));
  }

  {
    auto lower = std::make_unique<mtc::stages::MoveRelative>("lower object", cartesian_planner);
    lower->properties().configureInitFrom(mtc::Stage::PARENT);
    lower->setGroup(arm_group_name_);
    geometry_msgs::msg::Vector3Stamped direction;
    direction.header.frame_id = kHandFrame;
    direction.vector.z = -1.0;
    lower->setDirection(direction);
    lower->setMinMaxDistance(0.0, approach_min_distance_);
    place_container->add(std::move(lower));
  }

  {
    auto open_after_place = std::make_unique<mtc::stages::MoveTo>("open hand (place)", interpolation_planner);
    open_after_place->setGroup(gripper_group_name_);
    open_after_place->setGoal(gripper_open_pose_);
    place_container->add(std::move(open_after_place));
  }

  {
    auto forbid_collision = std::make_unique<mtc::stages::ModifyPlanningScene>("forbid grasp collision");
    forbid_collision->allowCollisions(object_id_, kGripperBodyLink, false);
    forbid_collision->allowCollisions(object_id_, kHandFrame, false);
    forbid_collision->allowCollisions(object_id_, kJawLink, false);
    place_container->add(std::move(forbid_collision));
  }

  {
    auto detach = std::make_unique<mtc::stages::ModifyPlanningScene>("detach object");
    detach->detachObject(object_id_, kHandFrame);
    place_container->add(std::move(detach));
  }

  {
    auto retreat = std::make_unique<mtc::stages::MoveRelative>("retreat", cartesian_planner);
    retreat->properties().configureInitFrom(mtc::Stage::PARENT);
    retreat->setGroup(arm_group_name_);
    geometry_msgs::msg::Vector3Stamped direction;
    direction.header.frame_id = kHandFrame;
    direction.vector.z = 1.0;
    retreat->setDirection(direction);
    retreat->setMinMaxDistance(0.02, retreat_distance_);
    place_container->add(std::move(retreat));
  }

  {
    auto return_home = std::make_unique<mtc::stages::MoveTo>("return home", sampling_planner);
    return_home->setGroup(arm_group_name_);
    return_home->setGoal(home_pose_name_);
    place_container->add(std::move(return_home));
  }

  task.add(std::move(place_container));

  return task;
}

int main(int argc, char** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions options;
  options.automatically_declare_parameters_from_overrides(true);

  auto planner = std::make_shared<So101Planner>(options);
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(planner->getNodeBaseInterface());
  executor.spin();
  executor.remove_node(planner->getNodeBaseInterface());
  rclcpp::shutdown();
  return 0;
}
