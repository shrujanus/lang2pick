from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, Command, PathSubstitution
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_rviz", default_value="true", description="Show robot description"
            ),
            DeclareLaunchArgument("description", default_value="so101.urdf.xacro"),
            DeclareLaunchArgument("rviz_config", default_value="so101.rviz"),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[
                    {
                        "robot_description": ParameterValue(
                            Command(
                                (
                                    "xacro",
                                    " ",
                                    PathSubstitution(
                                        FindPackageShare("so101_description")
                                    )
                                    / "urdf"
                                    / LaunchConfiguration("description"),
                                )
                            ),
                            value_type=str,
                        ),
                    }
                ],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                output="screen",
                arguments=[
                    "-d",
                    PathSubstitution(FindPackageShare("so101_description"))
                    / "config"
                    / LaunchConfiguration("rviz_config"),
                ],
                condition=IfCondition(LaunchConfiguration("use_rviz")),
            ),
            Node(
                package="joint_state_publisher_gui",
                executable="joint_state_publisher_gui",
                output="screen",
                parameters=[
                    {
                        "robot_description": ParameterValue(
                            Command(
                                (
                                    "xacro",
                                    " ",
                                    PathSubstitution(
                                        FindPackageShare("so101_description")
                                    )
                                    / "urdf"
                                    / LaunchConfiguration("description"),
                                )
                            ),
                            value_type=str,
                        ),
                    }
                ],
            ),
        ]
    )
