from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pointcloud_topic = LaunchConfiguration("depth_pointcloud_topic")
    workspace_topic = LaunchConfiguration("workspace_pointcloud_topic")
    octomap_resolution = LaunchConfiguration("octomap_resolution")

    declare_pointcloud = DeclareLaunchArgument(
        "depth_pointcloud_topic", default_value="/camera/depth/color/points",
        description="Point cloud topic provided by the depth camera")
    declare_workspace_topic = DeclareLaunchArgument(
        "workspace_pointcloud_topic", default_value="/workspace/points",
        description="Filtered point cloud topic used for GPD and octomap")
    declare_octomap_res = DeclareLaunchArgument(
        "octomap_resolution", default_value="0.02", description="Octomap resolution in meters")

    camera_node = Node(
        package="realsense2_camera",
        executable="realsense2_camera_node",
        name="realsense2_camera",
        output="screen",
        parameters=[{
            "enable_color": True,
            "enable_depth": True,
            "pointcloud.enable": True,
            "pointcloud.stream_filter": 2,
            "pointcloud.stream_index_filter": 0,
            "rgb_camera.profile": "640x480x30",
            "depth_module.profile": "640x480x30",
        }]
    )

    crop_node = Node(
        package="so101_planner",
        executable="pointcloud_crop_box_node",
        name="workspace_crop_box",
        parameters=[{
            "input_topic": pointcloud_topic,
            "output_topic": workspace_topic,
            "min_bounds": [-0.30, -0.30, 0.00],
            "max_bounds": [0.30, 0.30, 0.50],
            "target_frame": "world",
            "use_sim_time": True,
        }],
        remappings=[]
    )

    octomap_node = Node(
        package="octomap_server",
        executable="octomap_server_node",
        name="octomap_server",
        output="screen",
        parameters=[{
            "frame_id": "world",
            "resolution": octomap_resolution,
            "compress_map": False,
            "use_sim_time": True,
        }],
        remappings=[("cloud_in", workspace_topic)]
    )

    gpd_config_path = PathJoinSubstitution([FindPackageShare("so101_planner"), "config", "gpd_cfg.yaml"])
    gpd_node = Node(
        package="so101_planner",
        executable="gpd_grasp_detector_node",
        name="gpd_grasp_detector",
        output="screen",
        parameters=[{
            "pointcloud_topic": workspace_topic,
            "camera_frame": "world",
            "gpd_config_path": gpd_config_path,
            "crop_box_size": [0.30, 0.30, 0.25],
            "gripper_joint_names": ["left_finger_joint", "right_finger_joint"],
            "gripper_open_positions": [0.04, 0.04],
            "gripper_closed_positions": [0.0, 0.0],
            "use_sim_time": True,
        }]
    )

    planner_node = Node(
        package="so101_planner",
        executable="so101_planner_node",
        name="perception_mtc_planner",
        output="screen",
        parameters=[{
            "octomap_topic": "/octomap_binary",
            "gpd_service_name": "/detect_grasps",
            "ik_frame_link": "gripper_link",
            "ik_frame_translation": [0.0, 0.0, 0.0],
            "ik_frame_rpy": [0.0, 0.0, 0.0],
            "use_sim_time": True,
        }]
    )

    return LaunchDescription([
        declare_pointcloud,
        declare_workspace_topic,
        declare_octomap_res,
        # camera_node,
        crop_node,
        octomap_node,
        gpd_node,
        planner_node,
    ])
