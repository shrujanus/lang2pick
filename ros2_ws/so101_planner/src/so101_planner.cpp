#include <so101_planner/so101_planner.hpp>

#include <cmath>
#include <functional>
#include <utility>

#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <moveit/planning_scene/planning_scene.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit/task_constructor/solvers.h>
#include <moveit/task_constructor/stages.h>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
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

static const rclcpp::Logger LOGGER = rclcpp::get_logger("so101_planner");

rclcpp::node_interfaces::NodeBaseInterface::SharedPtr So101Planner::getNodeBaseInterface()
{
  return node_->get_node_base_interface();
}

So101Planner::So101Planner(const rclcpp::NodeOptions& options)
  : node_{ std::make_shared<rclcpp::Node>("so101_planner", options) }
{
  using std::placeholders::_1;
  using std::placeholders::_2;
  using std::placeholders::_3;

  tf_buffer_ = std::make_shared<tf2_ros::Buffer>(node_->get_clock());
  tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_, node_);

  pick_place_service_ = node_->create_service<::so101_planner::srv::PickPlace>(
      "pick_place", std::bind(&So101Planner::handlePickPlaceRequest, this, _1, _2, _3));

  loadParameters();
}

void So101Planner::loadParameters()
{
  auto get_param = [this](const std::string& name, auto default_value) {
    using ParamType = decltype(default_value);
    if (node_->has_parameter(name))
    {
      return node_->get_parameter(name).template get_value<ParamType>();
    }
    return node_->declare_parameter<ParamType>(name, default_value);
  };

  arm_group_name_ = get_param("arm_group_name", arm_group_name_);
  gripper_group_name_ = get_param("gripper_group_name", gripper_group_name_);
  gripper_open_pose_ = get_param("gripper_open_pose", gripper_open_pose_);
  gripper_close_pose_ = get_param("gripper_close_pose", gripper_close_pose_);
  home_pose_name_ = get_param("home_pose_name", home_pose_name_);
  planning_attempts_ = get_param("planning_attempts", planning_attempts_);
}

bool So101Planner::transformPoseToWorld(const geometry_msgs::msg::PoseStamped& input,
                                        geometry_msgs::msg::PoseStamped& output)
{
  output = input;
  if (output.header.frame_id.empty())
  {
    output.header.frame_id = kWorldFrame;
    if (output.pose.orientation.x == 0.0 && output.pose.orientation.y == 0.0 && output.pose.orientation.z == 0.0 &&
        output.pose.orientation.w == 0.0)
    {
      output.pose.orientation.w = 1.0;
    }
    return true;
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
    const auto timeout = rclcpp::Duration::from_seconds(2.5);
    const auto transform = tf_buffer_->lookupTransform(kWorldFrame, output.header.frame_id, rclcpp::Time(0), timeout);
    tf2::doTransform(input, output, transform);
    output.header.frame_id = kWorldFrame;
    return true;
  }
  catch (const tf2::TransformException& ex)
  {
    RCLCPP_ERROR(LOGGER, "Failed to transform pose from frame '%s' to '%s': %s", input.header.frame_id.c_str(),
                 kWorldFrame, ex.what());
    return false;
  }
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

  setupPlanningScene(pick_pose_);
  const bool success = doTask();
  response->success = success;
  response->message = success ? "Pick and place completed." : "Pick and place failed.";
}

void So101Planner::setupPlanningScene(const geometry_msgs::msg::PoseStamped& object_pose)
{
  moveit_msgs::msg::CollisionObject object;
  object.id = object_id_;
  object.header.frame_id = object_pose.header.frame_id.empty() ? kWorldFrame : object_pose.header.frame_id;
  object.primitives.resize(1);
  object.primitives[0].type = shape_msgs::msg::SolidPrimitive::CYLINDER;
  object.primitives[0].dimensions = { 0.06, 0.02 };

  object.pose = object_pose.pose;
  if (object.pose.orientation.x == 0.0 && object.pose.orientation.y == 0.0 && object.pose.orientation.z == 0.0 &&
      object.pose.orientation.w == 0.0)
  {
    object.pose.orientation.w = 1.0;
  }

  moveit::planning_interface::PlanningSceneInterface psi;
  psi.applyCollisionObject(object);
}

bool So101Planner::doTask()
{
  task_ = createTask();

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
    RCLCPP_ERROR_STREAM(LOGGER, "Task planning failed");

    auto root = task_.stages();
    const auto& children = root->numChildren();
    (void)children;
    return false;
  }

  if (task_.solutions().empty())
  {
    RCLCPP_ERROR_STREAM(LOGGER, "No task solutions were generated");
    return false;
  }

  auto& first_solution = *task_.solutions().front();

  task_.introspection().publishSolution(first_solution);

  auto result = task_.execute(first_solution);
  if (result.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS)
  {
    RCLCPP_ERROR_STREAM(LOGGER, "Task execution failed");
    return false;
  }

  return true;
}

mtc::Task So101Planner::createTask()
{
  mtc::Task task;
  task.stages()->setName("so101 pick and place");
  task.loadRobotModel(node_);

  const double pi = 3.14159265358979323846;
  const double half_pi = pi / 2.0;

  geometry_msgs::msg::PoseStamped ik_frame_pose;
  ik_frame_pose.header.frame_id = kGripperBodyLink;
  constexpr double object_height = 0.06;
  constexpr double object_radius = 0.02;
  ik_frame_pose.pose.position.z = -(round(object_height / 2.0) + 0.1);  // round up
  ik_frame_pose.pose.position.x = abs(object_radius - 0.04);

  auto ensureOrientation = [](geometry_msgs::msg::Quaternion& q) {
    if (q.x == 0.0 && q.y == 0.0 && q.z == 0.0 && q.w == 0.0)
    {
      q.w = 1.0;
    }
  };

  task.setProperty("group", arm_group_name_);
  task.setProperty("eef", gripper_group_name_);
  task.setProperty("ik_frame", ik_frame_pose);
  task.setProperty("object", object_id_);
  task.setProperty("global_frame", kWorldFrame);

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
  mtc::Stage* current_state_ptr = nullptr;
#pragma GCC diagnostic pop

  auto stage_state_current = std::make_unique<mtc::stages::CurrentState>("current");
  current_state_ptr = stage_state_current.get();
  task.add(std::move(stage_state_current));

  auto sampling_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node_);
  auto interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();

  auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
  cartesian_planner->setMaxVelocityScalingFactor(1.0);
  cartesian_planner->setMaxAccelerationScalingFactor(1.0);
  cartesian_planner->setStepSize(0.005);

  auto stage_open_hand = std::make_unique<mtc::stages::MoveTo>("open hand", interpolation_planner);
  stage_open_hand->setGroup(gripper_group_name_);
  stage_open_hand->setGoal(gripper_open_pose_);
  task.add(std::move(stage_open_hand));

  auto stage_move_to_pick = std::make_unique<mtc::stages::Connect>(
      "move to pick", mtc::stages::Connect::GroupPlannerVector{ { arm_group_name_, sampling_planner } });
  stage_move_to_pick->setTimeout(5.0);
  stage_move_to_pick->properties().configureInitFrom(mtc::Stage::PARENT);
  task.add(std::move(stage_move_to_pick));
  mtc::Stage* attach_object_stage = nullptr;

  tf2::Quaternion top_down_orientation;
  top_down_orientation.setRPY(pi, 0.0, half_pi);
  const auto top_down_orientation_msg = tf2::toMsg(top_down_orientation);

  geometry_msgs::msg::PoseStamped grasp_pose = pick_pose_;
  grasp_pose.header.frame_id = kWorldFrame;
  // ensureOrientation(grasp_pose.pose.orientation);

  grasp_pose.pose.orientation = top_down_orientation_msg;

  auto stage_generate_grasp = std::make_unique<mtc::stages::GenerateGraspPose>("generate grasp pose");
  stage_generate_grasp->properties().configureInitFrom(mtc::Stage::PARENT);
  stage_generate_grasp->properties().set("marker_ns", "grasp_pose");
  stage_generate_grasp->properties().set("object", object_id_);
  stage_generate_grasp->setPreGraspPose(gripper_open_pose_);
  stage_generate_grasp->setGraspPose(gripper_close_pose_);
  stage_generate_grasp->setAngleDelta(pi / 24.0);
  stage_generate_grasp->setMonitoredStage(current_state_ptr);
  stage_generate_grasp->setPose(grasp_pose);

  auto stage_grasp = std::make_unique<mtc::stages::ComputeIK>("compute grasp IK", std::move(stage_generate_grasp));
  stage_grasp->properties().configureInitFrom(mtc::Stage::PARENT, { "group", "eef", "ik_frame" });
  stage_grasp->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
  stage_grasp->setMaxIKSolutions(8);
  stage_grasp->setMinSolutionDistance(0.05);
  stage_grasp->setIKFrame(ik_frame_pose);
  task.add(std::move(stage_grasp));

  auto stage_approach = std::make_unique<mtc::stages::MoveRelative>("approach object", cartesian_planner);
  stage_approach->properties().configureInitFrom(mtc::Stage::PARENT);
  stage_approach->setGroup(arm_group_name_);
  geometry_msgs::msg::Vector3Stamped approach_direction;
  approach_direction.header.frame_id = kHandFrame;
  // approach_direction.vector.z = -1.0;
  stage_approach->setDirection(approach_direction);
  stage_approach->setMinMaxDistance(0.0, 0.12);
  task.add(std::move(stage_approach));

  auto stage_allow_collision = std::make_unique<mtc::stages::ModifyPlanningScene>("allow object collision");
  stage_allow_collision->allowCollisions(object_id_, kGripperBodyLink, true);
  stage_allow_collision->allowCollisions(object_id_, kHandFrame, true);
  stage_allow_collision->allowCollisions(object_id_, kJawLink, true);
  task.add(std::move(stage_allow_collision));

  auto stage_close_hand = std::make_unique<mtc::stages::MoveTo>("close hand", interpolation_planner);
  stage_close_hand->setGroup(gripper_group_name_);
  stage_close_hand->setGoal(gripper_close_pose_);
  task.add(std::move(stage_close_hand));

  auto stage_attach_object = std::make_unique<mtc::stages::ModifyPlanningScene>("attach object");
  stage_attach_object->attachObject(object_id_, kHandFrame);
  attach_object_stage = stage_attach_object.get();
  task.add(std::move(stage_attach_object));

  auto stage_lift = std::make_unique<mtc::stages::MoveRelative>("lift object", cartesian_planner);
  stage_lift->properties().configureInitFrom(mtc::Stage::PARENT);
  stage_lift->setGroup(arm_group_name_);
  geometry_msgs::msg::Vector3Stamped lift_direction;
  lift_direction.header.frame_id = kBaseLink;
  lift_direction.vector.z = 1.0;
  stage_lift->setDirection(lift_direction);
  stage_lift->setMinMaxDistance(0.0, 0.12);
  task.add(std::move(stage_lift));

  auto stage_move_to_place = std::make_unique<mtc::stages::Connect>(
      "move to place", mtc::stages::Connect::GroupPlannerVector{ { arm_group_name_, sampling_planner } });
  stage_move_to_place->setTimeout(5.0);
  stage_move_to_place->properties().configureInitFrom(mtc::Stage::PARENT);
  task.add(std::move(stage_move_to_place));

  auto place_container = std::make_unique<mtc::SerialContainer>("place object");
  task.properties().exposeTo(place_container->properties(), { "group", "eef", "ik_frame", "object" });
  place_container->properties().configureInitFrom(mtc::Stage::PARENT, { "group", "eef", "ik_frame", "object" });
  place_container->properties().set("object", object_id_);

  geometry_msgs::msg::PoseStamped place_pose = place_pose_;
  place_pose.header.frame_id = kWorldFrame;
  place_pose.pose.orientation = top_down_orientation_msg;
  place_pose.pose.position.z += object_height / 2.0;

  geometry_msgs::msg::PoseStamped ik_frame_pose_fixed = ik_frame_pose;
  ik_frame_pose_fixed.pose.orientation = top_down_orientation_msg;
  task.setProperty("ik_frame", ik_frame_pose_fixed);

  {
    auto stage_generate_place = std::make_unique<mtc::stages::GeneratePlacePose>("generate place pose");
    stage_generate_place->properties().configureInitFrom(mtc::Stage::PARENT);
    stage_generate_place->properties().set("marker_ns", "place_pose");
    stage_generate_place->properties().set("object", object_id_);
    stage_generate_place->setPose(place_pose);
    stage_generate_place->setMonitoredStage(attach_object_stage);

    auto stage_place = std::make_unique<mtc::stages::ComputeIK>("compute place IK", std::move(stage_generate_place));
    stage_place->properties().configureInitFrom(mtc::Stage::PARENT, { "group", "eef", "ik_frame" });
    stage_place->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
    stage_place->setMaxIKSolutions(8);
    stage_place->setMinSolutionDistance(0.05);
    stage_place->setIKFrame(ik_frame_pose_fixed);
    place_container->add(std::move(stage_place));
  }

  {
    auto stage_lower = std::make_unique<mtc::stages::MoveRelative>("lower object", cartesian_planner);
    stage_lower->properties().configureInitFrom(mtc::Stage::PARENT);
    stage_lower->setGroup(arm_group_name_);
    geometry_msgs::msg::Vector3Stamped lower_direction;
    lower_direction.header.frame_id = kHandFrame;
    lower_direction.vector.z = -1.0;
    stage_lower->setDirection(lower_direction);
    stage_lower->setMinMaxDistance(0.0, 0.02);
    place_container->add(std::move(stage_lower));
  }

  {
    auto stage_open_after_place = std::make_unique<mtc::stages::MoveTo>("open hand (place)", interpolation_planner);
    stage_open_after_place->setGroup(gripper_group_name_);
    stage_open_after_place->setGoal(gripper_open_pose_);
    place_container->add(std::move(stage_open_after_place));
  }

  {
    auto stage_forbid_collision = std::make_unique<mtc::stages::ModifyPlanningScene>("forbid object collision");
    stage_forbid_collision->allowCollisions(object_id_, kGripperBodyLink, false);
    stage_forbid_collision->allowCollisions(object_id_, kHandFrame, false);
    stage_forbid_collision->allowCollisions(object_id_, kJawLink, false);
    place_container->add(std::move(stage_forbid_collision));
  }

  {
    auto stage_detach = std::make_unique<mtc::stages::ModifyPlanningScene>("detach object");
    stage_detach->detachObject(object_id_, kHandFrame);
    place_container->add(std::move(stage_detach));
  }

  {
    auto stage_retract = std::make_unique<mtc::stages::MoveRelative>("retreat", cartesian_planner);
    stage_retract->properties().configureInitFrom(mtc::Stage::PARENT);
    stage_retract->setGroup(arm_group_name_);
    geometry_msgs::msg::Vector3Stamped retreat_direction;
    retreat_direction.header.frame_id = kHandFrame;
    retreat_direction.vector.z = 1.0;
    stage_retract->setDirection(retreat_direction);
    stage_retract->setMinMaxDistance(0.0, 0.15);
    place_container->add(std::move(stage_retract));
  }

  {
    auto stage_return_home = std::make_unique<mtc::stages::MoveTo>("return to init", sampling_planner);
    stage_return_home->setGroup(arm_group_name_);
    stage_return_home->setGoal(home_pose_name_);
    place_container->add(std::move(stage_return_home));
  }

  task.add(std::move(place_container));

  return task;
}

int main(int argc, char** argv)
{
  rclcpp::init(argc, argv);

  rclcpp::NodeOptions options;
  options.automatically_declare_parameters_from_overrides(true);

  auto mtc_task_node = std::make_shared<So101Planner>(options);
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(mtc_task_node->getNodeBaseInterface());
  executor.spin();
  executor.remove_node(mtc_task_node->getNodeBaseInterface());

  rclcpp::shutdown();
  return 0;
}
