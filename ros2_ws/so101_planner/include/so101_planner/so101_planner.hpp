#ifndef SO101_PLANNER__SO101_PLANNER_HPP_
#define SO101_PLANNER__SO101_PLANNER_HPP_

#include <memory>
#include <mutex>
#include <string>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <moveit/task_constructor/task.h>
#include <moveit_msgs/msg/collision_object.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rmw/types.h>

#include <so101_planner/srv/pick_place.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>

namespace mtc = moveit::task_constructor;

class So101Planner
{
public:
  explicit So101Planner(const rclcpp::NodeOptions& options);

  rclcpp::node_interfaces::NodeBaseInterface::SharedPtr getNodeBaseInterface();

private:
  void loadParameters();
  void setupPlanningScene(const geometry_msgs::msg::PoseStamped& object_pose);
  bool doTask();
  mtc::Task createTask();
  bool transformPoseToWorld(const geometry_msgs::msg::PoseStamped& input, geometry_msgs::msg::PoseStamped& output);

  void handlePickPlaceRequest(const std::shared_ptr<rmw_request_id_t> request_header,
                              const std::shared_ptr<::so101_planner::srv::PickPlace::Request> request,
                              std::shared_ptr<::so101_planner::srv::PickPlace::Response> response);

  mtc::Task task_;
  rclcpp::Node::SharedPtr node_;
  std::shared_ptr<tf2_ros::Buffer> tf_buffer_;
  std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
  rclcpp::Service<::so101_planner::srv::PickPlace>::SharedPtr pick_place_service_;
  geometry_msgs::msg::PoseStamped pick_pose_;
  geometry_msgs::msg::PoseStamped place_pose_;
  std::string object_id_ = "object";
  std::mutex task_mutex_;

  std::string arm_group_name_ = "so101_arm";
  std::string gripper_group_name_ = "gripper";
  std::string gripper_open_pose_ = "gripper_open";
  std::string gripper_close_pose_ = "gripper_close";
  std::string home_pose_name_ = "init";
  int planning_attempts_ = 10;

  inline static constexpr const char* kWorldFrame = "world";
  inline static constexpr const char* kBaseLink = "base_link";
  inline static constexpr const char* kHandFrame = "gripper_frame_link";
  inline static constexpr const char* kGripperBodyLink = "gripper_link";
  inline static constexpr const char* kJawLink = "moving_jaw_so101_v1_link";
};

#endif  // SO101_PLANNER__SO101_PLANNER_HPP_
