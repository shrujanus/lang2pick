from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import SetParameter
from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_moveit_rviz_launch


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    moveit_config = MoveItConfigsBuilder(
        "so101_robot", package_name="so101_motion"
    ).to_moveit_configs()

    rviz_ld = generate_moveit_rviz_launch(moveit_config)

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_sim_time", default_value="true", description="Use simulation clock"
            ),
            SetParameter(name="use_sim_time", value=use_sim_time),
            *rviz_ld.entities,
        ]
    )
