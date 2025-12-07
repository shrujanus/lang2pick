cmake_minimum_required(VERSION 3.8)
project(so101_planner)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(moveit_task_constructor_core REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(octomap_msgs REQUIRED)
find_package(pcl_conversions REQUIRED)
find_package(pcl_ros REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(tf2_eigen REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(OpenCV REQUIRED)

# GPD is required for the MTC pipeline; fail fast if headers/libs are missing.
if(NOT GPD_INCLUDE_DIR)
  find_path(GPD_INCLUDE_DIR NAMES gpd/util/cloud.h
    PATHS
      ${CMAKE_CURRENT_SOURCE_DIR}/../gpd/include
      ${CMAKE_CURRENT_SOURCE_DIR}/../../gpd/include
      ${CMAKE_CURRENT_SOURCE_DIR}/../../install/gpd/include
      ${CMAKE_CURRENT_SOURCE_DIR}/../../../install/gpd/include
      ${CMAKE_SOURCE_DIR}/../gpd/include
      /root/dev_ws/src/gpd/include
      /root/dev_ws/install/gpd/include
  )
endif()
if(NOT GPD_INCLUDE_DIR)
  message(FATAL_ERROR "GPD headers not found. Install GPD (gpd/util/cloud.h) and re-run colcon build.")
endif()

if(NOT GPD_LIBRARY)
  find_library(GPD_LIBRARY NAMES gpd
    PATHS
      ${CMAKE_CURRENT_SOURCE_DIR}/../../install/gpd/lib
      ${CMAKE_CURRENT_SOURCE_DIR}/../../../install/gpd/lib
      /root/dev_ws/install/gpd/lib
  )
endif()
if(NOT GPD_LIBRARY)
  message(FATAL_ERROR "GPD library not found. Build gpd and re-run colcon build.")
endif()

set(MSG_DEPENDENCIES geometry_msgs moveit_msgs)
rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/PickPlace.srv"
  "srv/DetectGrasps.srv"
  "srv/BoundingBoxPickPlace.srv"
  DEPENDENCIES ${MSG_DEPENDENCIES}
)

add_executable(so101_planner_node src/so101_planner.cpp)
ament_target_dependencies(so101_planner_node
  geometry_msgs
  moveit_msgs
  moveit_task_constructor_core
  moveit_ros_planning_interface
  octomap_msgs
  rclcpp
  sensor_msgs
  tf2_eigen
  tf2_geometry_msgs
  tf2_ros
)
target_include_directories(so101_planner_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(so101_planner_node PUBLIC c_std_99 cxx_std_17)

add_executable(gpd_grasp_detector_node src/gpd_grasp_detector_node.cpp)
ament_target_dependencies(gpd_grasp_detector_node
  geometry_msgs
  moveit_msgs
  pcl_conversions
  pcl_ros
  ament_index_cpp
  rclcpp
  sensor_msgs
  trajectory_msgs
  tf2_eigen
)
target_include_directories(gpd_grasp_detector_node PRIVATE ${GPD_INCLUDE_DIR})
target_include_directories(gpd_grasp_detector_node PRIVATE ${OpenCV_INCLUDE_DIRS})
target_compile_features(gpd_grasp_detector_node PUBLIC c_std_99 cxx_std_17)
target_link_libraries(gpd_grasp_detector_node ${GPD_LIBRARY} ${OpenCV_LIBRARIES})

add_executable(pointcloud_crop_box_node src/pointcloud_crop_box_node.cpp)
ament_target_dependencies(pointcloud_crop_box_node
  pcl_conversions
  pcl_ros
  rclcpp
  sensor_msgs
)
target_compile_features(pointcloud_crop_box_node PUBLIC c_std_99 cxx_std_17)

rosidl_get_typesupport_target(cpp_typesupport_target
  ${PROJECT_NAME}
  "rosidl_typesupport_cpp")
target_link_libraries(so101_planner_node ${cpp_typesupport_target})
if(TARGET gpd_grasp_detector_node)
  target_link_libraries(gpd_grasp_detector_node ${cpp_typesupport_target})
endif()

install(TARGETS so101_planner_node
  DESTINATION lib/${PROJECT_NAME})
install(TARGETS pointcloud_crop_box_node
  DESTINATION lib/${PROJECT_NAME})
if(TARGET gpd_grasp_detector_node)
  install(TARGETS gpd_grasp_detector_node
    DESTINATION lib/${PROJECT_NAME})
endif()

install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})

install(DIRECTORY include/
  DESTINATION include
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_export_dependencies(rosidl_default_runtime)

ament_package()
