from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, Command, PathSubstitution
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.event_handlers import OnProcessExit
from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_move_group_launch


def generate_launch_description():

    use_rviz_arg = DeclareLaunchArgument(
        "use_rviz", default_value="true", description="Show robot description"
    )
    description_arg = DeclareLaunchArgument(
        "description", default_value="so101.urdf.xacro"
    )
    rviz_config_arg = DeclareLaunchArgument("rviz_config", default_value="moveit.rviz")
    controller_config_arg = DeclareLaunchArgument(
        "controller_config", default_value="ros2_controllers.yaml"
    )
    robot_description = ParameterValue(
        Command(
            [
                "xacro ",
                PathSubstitution(FindPackageShare("so101_control"))
                / "config"
                / LaunchConfiguration("description"),
            ]
        )
    )

    robot_state_publisher_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[
            {
                "robot_description": robot_description,
            }
        ],
    )

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        output="screen",
        arguments=[
            "-d",
            PathSubstitution(FindPackageShare("so101_motion"))
            / "config"
            / LaunchConfiguration("rviz_config"),
        ],
        condition=IfCondition(LaunchConfiguration("use_rviz")),
    )

    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            PathSubstitution(FindPackageShare("so101_motion"))
            / "config"
            / LaunchConfiguration("controller_config")
        ],
        remappings=[("~/robot_description", "/robot_description")],
        output="both",
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        name="joint_state_broadcaster",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager",
            "/controller_manager",
        ],
    )

    robot_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        name="so101_arm_controller",
        arguments=[
            "so101_arm_controller",
            "--controller-manager",
            "/controller_manager",
        ],
    )

    delay_robot_controller_spawner = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[robot_controller_spawner],
        )
    )

    moveit_config = MoveItConfigsBuilder(
        "so101_robot", package_name="so101_motion"
    ).to_moveit_configs()

    return LaunchDescription(
        [
            use_rviz_arg,
            description_arg,
            rviz_config_arg,
            controller_config_arg,
            robot_state_publisher_node,
            rviz_node,
            ros2_control_node,
            joint_state_broadcaster_spawner,
            delay_robot_controller_spawner,
            generate_move_group_launch(moveit_config),
        ]
    )
