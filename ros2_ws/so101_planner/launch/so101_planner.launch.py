#!/usr/bin/env python3
"""Launch file for the So101 planner node."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    package_share = get_package_share_directory("so101_planner")
    params_file = os.path.join(package_share, "config", "so101_planner.yaml")

    planner_node = Node(
        package="so101_planner",
        executable="so101_planner_node",
        name="so101_planner",
        output="screen",
        parameters=[params_file],
    )

    return LaunchDescription([planner_node])
