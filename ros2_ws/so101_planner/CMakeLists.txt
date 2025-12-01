cmake_minimum_required(VERSION 3.8)
project(so101_planner)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(moveit_task_constructor_core REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(tf2_ros REQUIRED)

set(MSG_DEPENDENCIES geometry_msgs)
rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/PickPlace.srv"
  DEPENDENCIES ${MSG_DEPENDENCIES}
)

add_executable(so101_planner_node src/so101_planner.cpp)
ament_target_dependencies(so101_planner_node
  geometry_msgs
  moveit_msgs
  moveit_task_constructor_core
  rclcpp
  tf2_geometry_msgs
  tf2_ros
)
target_include_directories(so101_planner_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(so101_planner_node PUBLIC c_std_99 cxx_std_17)

rosidl_get_typesupport_target(cpp_typesupport_target
  ${PROJECT_NAME}
  "rosidl_typesupport_cpp")
target_link_libraries(so101_planner_node ${cpp_typesupport_target})

install(TARGETS so101_planner_node
  DESTINATION lib/${PROJECT_NAME})

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
