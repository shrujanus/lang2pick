import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    # Launch arguments
    use_rviz_arg = DeclareLaunchArgument(
        "use_rviz", default_value="true", description="Launch RViz with MoveIt"
    )
    usb_port_arg = DeclareLaunchArgument(
        "usb_port",
        default_value="/dev/ttyACM0",
        description="USB port for robot connection",
    )

    use_rviz = LaunchConfiguration("use_rviz")

    # Package directories
    motion_share = get_package_share_directory("so101_motion")
    control_share = get_package_share_directory("so101_control")

    # Robot description from xacro for real hardware
    xacro_file = os.path.join(control_share, "config", "so101.urdf.xacro")
    controller_config_file = os.path.join(
        motion_share, "config", "ros2_controllers.yaml"
    )

    robot_description = Command(
        [
            "xacro ",
            xacro_file,
            " use_gazebo:=false",
            " use_mock_hardware:=false",
            " controller_config_file:=",
            controller_config_file,
        ]
    )

    # MoveIt configuration for real robot
    moveit_config = (
        MoveItConfigsBuilder("so101_robot", package_name="so101_motion")
        .robot_description(
            file_path=xacro_file,
            mappings={
                "use_gazebo": "false",
                "use_mock_hardware": "false",
                "controller_config_file": controller_config_file,
            },
        )
        .robot_description_semantic(
            file_path=os.path.join(motion_share, "config", "so101_robot.srdf")
        )
        .trajectory_execution(
            file_path=os.path.join(motion_share, "config", "moveit_controllers.yaml")
        )
        .planning_pipelines(pipelines=["ompl"])
        .to_moveit_configs()
    )

    # Robot state publisher
    robot_state_publisher_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": robot_description}],
        output="screen",
    )

    # ros2_control node for real hardware
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            {"robot_description": robot_description},
            controller_config_file,
        ],
        output="both",
    )

    # Controller spawners
    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager",
            "/controller_manager",
        ],
    )

    arm_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "so101_arm_controller",
            "--controller-manager",
            "/controller_manager",
        ],
    )

    gripper_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["gripper_controller", "--controller-manager", "/controller_manager"],
    )

    # MoveIt move_group node
    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            {"use_sim_time": False},
            {"trajectory_execution.allowed_execution_duration_scaling": 2.0},
            {"publish_robot_description_semantic": True},
        ],
    )

    # Static TF for world to base_link (virtual joint)
    world_to_base_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        arguments=["0", "0", "0", "0", "0", "0", "world", "base_link"],
    )

    # RViz with MoveIt configuration
    rviz_config_file = os.path.join(motion_share, "config", "moveit.rviz")
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        output="screen",
        arguments=["-d", rviz_config_file],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            moveit_config.joint_limits,
        ],
        condition=IfCondition(use_rviz),
    )

    # Event handlers for sequencing
    delay_joint_state_broadcaster = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=ros2_control_node,
            on_exit=[joint_state_broadcaster_spawner],
        )
    )

    delay_arm_controller = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[arm_controller_spawner, gripper_controller_spawner],
        )
    )

    delay_move_group = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=arm_controller_spawner,
            on_exit=[move_group_node],
        )
    )

    delay_rviz = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=arm_controller_spawner,
            on_exit=[rviz_node],
        )
    )

    return LaunchDescription(
        [
            use_rviz_arg,
            usb_port_arg,
            robot_state_publisher_node,
            ros2_control_node,
            world_to_base_tf,
            delay_joint_state_broadcaster,
            delay_arm_controller,
            delay_move_group,
            delay_rviz,
        ]
    )
