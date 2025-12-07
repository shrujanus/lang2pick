import os
import tempfile
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
    SetLaunchConfiguration,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    EnvironmentVariable,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
    TextSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _box_sdf(name: str, size_xyz: str, color_rgba: str) -> str:
    return (
        "<sdf version='1.7'>"
        "<model name='" + name + "'>"
        "<static>false</static>"
        "<pose>0 0 0 0 0 0</pose>"
        "<link name='link'>"
        "<inertial><mass>0.1</mass></inertial>"
        "<collision name='collision'><geometry><box><size>" + size_xyz + "</size></box></geometry></collision>"
        "<visual name='visual'><geometry><box><size>" + size_xyz + "</size></box></geometry>"
        "<material><ambient>" + color_rgba + "</ambient><diffuse>" + color_rgba + "</diffuse></material>"
        "</visual>"
        "</link>"
        "</model>"
        "</sdf>"
    )


def _write_robot_description_file(context, *args, **kwargs):
    description = context.launch_configurations.get("robot_description", "")
    temp_dir = os.path.join(tempfile.gettempdir(), "so101_sim")
    os.makedirs(temp_dir, exist_ok=True)
    robot_file = os.path.join(temp_dir, "so101.urdf")
    with open(robot_file, "w", encoding="utf-8") as urdf_file:
        urdf_file.write(description)
    return [SetLaunchConfiguration("robot_description_file", robot_file)]

def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    world = LaunchConfiguration("world")
    gui = LaunchConfiguration("gui")
    verbosity = LaunchConfiguration("gz_verbosity")
    robot_description = LaunchConfiguration("robot_description")
    robot_description_file = LaunchConfiguration("robot_description_file")

    robot_x = LaunchConfiguration("robot_x")
    robot_y = LaunchConfiguration("robot_y")
    robot_z = LaunchConfiguration("robot_z")
    robot_roll = LaunchConfiguration("robot_roll")
    robot_pitch = LaunchConfiguration("robot_pitch")
    robot_yaw = LaunchConfiguration("robot_yaw")

    camera_x = LaunchConfiguration("camera_x")
    camera_y = LaunchConfiguration("camera_y")
    camera_z = LaunchConfiguration("camera_z")
    camera_roll = LaunchConfiguration("camera_roll")
    camera_pitch = LaunchConfiguration("camera_pitch")
    camera_yaw = LaunchConfiguration("camera_yaw")

    declare_world = DeclareLaunchArgument(
        "world",
        default_value="so101_test.world",
        description="Ignition world file located in so101_bringup/worlds",
    )

    declare_use_sim_time = DeclareLaunchArgument(
        "use_sim_time", default_value="true", description="Use simulation clock"
    )

    declare_gui = DeclareLaunchArgument(
        "gui", default_value="true", description="Launch Gazebo GUI"
    )

    declare_verbosity = DeclareLaunchArgument(
        "gz_verbosity", default_value="4", description="Gazebo log verbosity"
    )

    pose_args = [
        DeclareLaunchArgument("robot_x", default_value="0.0", description="Robot spawn X (m)"),
        DeclareLaunchArgument("robot_y", default_value="0.0", description="Robot spawn Y (m)"),
        DeclareLaunchArgument("robot_z", default_value="0.0", description="Robot spawn Z (m)"),
        DeclareLaunchArgument("robot_roll", default_value="0.0", description="Robot roll (rad)"),
        DeclareLaunchArgument("robot_pitch", default_value="0.0", description="Robot pitch (rad)"),
        DeclareLaunchArgument("robot_yaw", default_value="0.0", description="Robot yaw (rad)"),
        DeclareLaunchArgument("camera_x", default_value="0.0", description="Depth camera X (m)"),
        DeclareLaunchArgument("camera_y", default_value="0.0", description="Depth camera Y (m)"),
        DeclareLaunchArgument("camera_z", default_value="1.0", description="Depth camera Z (m)"),
        DeclareLaunchArgument("camera_roll", default_value="0.0", description="Depth camera roll (rad)"),
        DeclareLaunchArgument("camera_pitch", default_value="1.0", description="Depth camera pitch (rad)"),
        DeclareLaunchArgument("camera_yaw", default_value="0.0", description="Depth camera yaw (rad)"),
    ]

    # MoveIt2 and MTC launch arguments
    launch_moveit = LaunchConfiguration("launch_moveit")
    launch_rviz = LaunchConfiguration("launch_rviz")
    launch_mtc = LaunchConfiguration("launch_mtc")
    octomap_resolution = LaunchConfiguration("octomap_resolution")

    moveit_mtc_args = [
        DeclareLaunchArgument("launch_moveit", default_value="true", description="Launch MoveIt2 move_group"),
        DeclareLaunchArgument("launch_rviz", default_value="true", description="Launch MoveIt RViz"),
        DeclareLaunchArgument("launch_mtc", default_value="true", description="Launch MTC planner pipeline"),
        DeclareLaunchArgument("octomap_resolution", default_value="0.01", description="Octomap resolution (m)"),
    ]

    description_share = FindPackageShare("so101_description")
    xacro_file = PathJoinSubstitution(
        [FindPackageShare("so101_control"), "config", "so101.urdf.xacro"]
    )
    controller_config = PathJoinSubstitution(
        [FindPackageShare("so101_control"), "config", "so101.yaml"]
    )
    robot_description_command = Command(
        [
            FindExecutable(name="xacro"),
            " ",
            xacro_file,
            " ",
            "use_gazebo:=true",
            " ",
            "use_mock_hardware:=false",
            " ",
            "controller_config_file:=",
            controller_config,
        ]
    )
    set_robot_description = SetLaunchConfiguration("robot_description", robot_description_command)
    generate_robot_file = OpaqueFunction(function=_write_robot_description_file)

    world_path = PathJoinSubstitution(
        [FindPackageShare("so101_bringup"), "worlds", world]
    )
    
    # Get the full path to the description package install directory
    description_install_path = PathJoinSubstitution([description_share, ".."])
    
    set_gz_resource_path = SetEnvironmentVariable(
        name="GZ_SIM_RESOURCE_PATH",
        value=[
            EnvironmentVariable("GZ_SIM_RESOURCE_PATH", default_value=""),
            TextSubstitution(text=":"),
            description_share,
            TextSubstitution(text=":"),
            description_install_path,
        ],
    )
    set_ign_resource_path = SetEnvironmentVariable(
        name="IGN_GAZEBO_RESOURCE_PATH",
        value=[
            EnvironmentVariable("IGN_GAZEBO_RESOURCE_PATH", default_value=""),
            TextSubstitution(text=":"),
            description_share,
            TextSubstitution(text=":"),
            description_install_path,
        ],
    )

    # Set plugin path for gz_ros2_control (both old IGN_ and new GZ_ prefixes for compatibility)
    set_gz_plugin_path = SetEnvironmentVariable(
        name="GZ_SIM_SYSTEM_PLUGIN_PATH",
        value=[
            EnvironmentVariable("GZ_SIM_SYSTEM_PLUGIN_PATH", default_value=""),
            TextSubstitution(text=":/opt/ros/humble/lib"),
        ],
    )
    set_ign_plugin_path = SetEnvironmentVariable(
        name="IGN_GAZEBO_SYSTEM_PLUGIN_PATH",
        value=[
            EnvironmentVariable("IGN_GAZEBO_SYSTEM_PLUGIN_PATH", default_value=""),
            TextSubstitution(text=":/opt/ros/humble/lib"),
        ],
    )

    gz_gui = ExecuteProcess(
        condition=IfCondition(gui),
        cmd=[
            FindExecutable(name="ign"),
            "gazebo",
            "-r",
            "-v",
            verbosity,
            world_path,
        ],
        output="screen",
    )

    gz_headless = ExecuteProcess(
        condition=UnlessCondition(gui),
        cmd=[
            FindExecutable(name="ign"),
            "gazebo",
            "-r",
            "-s",
            "-v",
            verbosity,
            world_path,
        ],
        output="screen",
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{
            "robot_description": robot_description,
            "use_sim_time": use_sim_time,
            "publish_frequency": 50.0,
            "frame_prefix": "",
        }],
        output="screen",
    )

    spawn_so101 = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-name",
            "so101",
            "-x",
            robot_x,
            "-y",
            robot_y,
            "-z",
            robot_z,
            "-R",
            robot_roll,
            "-P",
            robot_pitch,
            "-Y",
            robot_yaw,
            "-file",
            robot_description_file,
        ],
        output="screen",
        parameters=[{"use_sim_time": use_sim_time}],
    )

    spawn_depth_camera = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-name",
            "depth_camera",
            "-x",
            camera_x,
            "-y",
            camera_y,
            "-z",
            camera_z,
            "-R",
            camera_roll,
            "-P",
            camera_pitch,
            "-Y",
            camera_yaw,
            "-file",
            PathJoinSubstitution(
                [FindPackageShare("so101_bringup"), "models", "depth_camera.sdf"]
            ),
        ],
        output="screen",
        parameters=[{"use_sim_time": use_sim_time}],
    )

    cube_size = "0.05 0.05 0.05"
    cubes = [
        ("cube_red", 0.55, -0.05, 0.415, "0.8 0.1 0.1 1.0"),
        ("cube_green", 0.65, 0.05, 0.415, "0.1 0.8 0.2 1.0"),
        ("cube_blue", 0.60, 0.15, 0.415, "0.1 0.3 0.9 1.0"),
    ]

    cube_spawners = [
        Node(
            package="ros_gz_sim",
            executable="create",
            arguments=[
                "-name",
                name,
                "-x",
                str(x),
                "-y",
                str(y),
                "-z",
                str(z),
                "-R",
                "0",
                "-P",
                "0",
                "-Y",
                "0",
                "-string",
                _box_sdf(name, cube_size, color),
            ],
            output="screen",
            parameters=[{"use_sim_time": use_sim_time}],
        )
        for name, x, y, z, color in cubes
    ]

    # Clock bridge
    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
        parameters=[{"use_sim_time": use_sim_time}],
        output="screen",
    )

    # RGBD camera bridge - topics are published at model level in Fortress
    # Using remappings to map from Gazebo topics to ROS2 topics
    rgbd_camera_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/rgbd_camera/image@sensor_msgs/msg/Image[gz.msgs.Image",
            "/rgbd_camera/depth_image@sensor_msgs/msg/Image[gz.msgs.Image",
            "/rgbd_camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo",
            "/rgbd_camera/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked",
        ],
        remappings=[
            ("/rgbd_camera/image", "/depth_camera/color/image_raw"),
            ("/rgbd_camera/depth_image", "/depth_camera/depth/image_raw"),
            ("/rgbd_camera/camera_info", "/depth_camera/color/camera_info"),
            ("/rgbd_camera/points", "/depth_camera/points"),
        ],
        parameters=[{"use_sim_time": use_sim_time}],
        output="screen",
    )

    depth_camera_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        arguments=[
            "--x", camera_x,
            "--y", camera_y,
            "--z", camera_z,
            "--roll", camera_roll,
            "--pitch", camera_pitch,
            "--yaw", camera_yaw,
            "--frame-id", "world",
            "--child-frame-id", "depth_camera_link",
        ],
        parameters=[{"use_sim_time": use_sim_time}],
    )

    # TF from depth_camera_link to the Gazebo sensor frame
    depth_camera_sensor_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        arguments=[
            "--x", "0",
            "--y", "0",
            "--z", "0",
            "--roll", "0",
            "--pitch", "0",
            "--yaw", "0",
            "--frame-id", "depth_camera_link",
            "--child-frame-id", "depth_camera/depth_camera_link/rgbd_camera",
        ],
        parameters=[{"use_sim_time": use_sim_time}],
    )

    # ROS2 Control node that manages controller_manager
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            controller_config,
            {"use_sim_time": use_sim_time},
        ],
        remappings=[("~/robot_description", "/robot_description")],
        output="screen",
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager", "/controller_manager",
            "--controller-manager-timeout", "60",
        ],
        parameters=[{"use_sim_time": use_sim_time}],
    )

    arm_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "so101_arm_controller",
            "--controller-manager", "/controller_manager",
            "--controller-manager-timeout", "60",
        ],
        parameters=[{"use_sim_time": use_sim_time}],
    )

    gripper_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "gripper_controller",
            "--controller-manager", "/controller_manager",
            "--controller-manager-timeout", "60",
        ],
        parameters=[{"use_sim_time": use_sim_time}],
    )

    # Use TimerAction to delay controller spawning until Gazebo ros2_control plugin is ready
    delay_joint_state_spawner = TimerAction(
        period=8.0,
        actions=[joint_state_broadcaster_spawner],
    )

    delay_arm_controllers = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[arm_controller_spawner, gripper_controller_spawner],
        )
    )

    # ==================== MoveIt2 Configuration ====================
    # Include MoveIt move_group launch file for proper initialization
    move_group_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("so101_motion"),
                "launch",
                "move_group.launch.py"
            ])
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
        condition=IfCondition(launch_moveit),
    )

    # Virtual joint TF publishers for MoveIt
    virtual_joint_tfs = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("so101_motion"),
                "launch",
                "static_virtual_joint_tfs.launch.py"
            ])
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
        condition=IfCondition(launch_moveit),
    )

    # Delay MoveIt until controllers are ready
    delay_move_group = TimerAction(
        period=20.0,
        actions=[virtual_joint_tfs, move_group_launch],
    )

    # MoveIt RViz - include launch file for proper setup
    moveit_rviz_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("so101_motion"),
                "launch",
                "moveit_rviz.launch.py"
            ])
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
        condition=IfCondition(launch_rviz),
    )

    delay_rviz = TimerAction(
        period=25.0,
        actions=[moveit_rviz_launch],
    )

    # ==================== MTC Perception Pipeline ====================
    # Point cloud crop box node - filters workspace area
    workspace_crop_node = Node(
        condition=IfCondition(launch_mtc),
        package="so101_planner",
        executable="pointcloud_crop_box_node",
        name="workspace_crop_box",
        parameters=[{
            "input_topic": "/depth_camera/points",
            "output_topic": "/workspace/points",
            "min_bounds": [-0.30, -0.30, 0.00],
            "max_bounds": [0.30, 0.30, 0.50],
            "target_frame": "world",
            "use_sim_time": use_sim_time,
        }],
        output="screen",
    )

    # GPD grasp detector node
    gpd_config_path = PathJoinSubstitution(
        [FindPackageShare("so101_planner"), "config", "gpd_cfg.yaml"]
    )
    gpd_grasp_node = Node(
        condition=IfCondition(launch_mtc),
        package="so101_planner",
        executable="gpd_grasp_detector_node",
        name="gpd_grasp_detector",
        parameters=[{
            "pointcloud_topic": "/workspace/points",
            "camera_frame": "world",
            "gpd_config_path": gpd_config_path,
            "crop_box_size": [0.30, 0.30, 0.25],
            "gripper_joint_names": ["left_finger_joint", "right_finger_joint"],
            "gripper_open_positions": [0.04, 0.04],
            "gripper_closed_positions": [0.0, 0.0],
            "use_sim_time": use_sim_time,
        }],
        output="screen",
    )

    # MTC Planner node
    planner_config = PathJoinSubstitution(
        [FindPackageShare("so101_planner"), "config", "so101_planner.yaml"]
    )
    mtc_planner_node = Node(
        condition=IfCondition(launch_mtc),
        package="so101_planner",
        executable="so101_planner_node",
        name="so101_planner",
        parameters=[
            planner_config,
            {
                "octomap_topic": "/octomap_binary",
                "gpd_service_name": "/detect_grasps",
                "ik_frame_link": "gripper_link",
                "use_sim_time": use_sim_time,
            },
        ],
        output="screen",
    )

    # Delay MTC pipeline until MoveIt is ready
    delay_mtc_pipeline = TimerAction(
        period=20.0,
        actions=[workspace_crop_node, gpd_grasp_node, mtc_planner_node],
    )

    return LaunchDescription(
        [
            declare_world,
            declare_use_sim_time,
            declare_gui,
            declare_verbosity,
            *pose_args,
            *moveit_mtc_args,
            set_gz_resource_path,
            set_ign_resource_path,
            set_gz_plugin_path,
            set_ign_plugin_path,
            set_robot_description,
            generate_robot_file,
            gz_gui,
            gz_headless,
            robot_state_publisher,
            spawn_so101,
            spawn_depth_camera,
            *cube_spawners,
            clock_bridge,
            rgbd_camera_bridge,
            depth_camera_tf,
            depth_camera_sensor_tf,
            ros2_control_node,
            delay_joint_state_spawner,
            delay_arm_controllers,
            delay_move_group,
            delay_rviz,
            delay_mtc_pipeline,
        ]
    )
