cmake_minimum_required(VERSION 3.8)
project(roamer_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/GoTo.action"
  "action/Home.action"
  "srv/GetStatus.srv"
  "srv/GetPosition.srv"
  "srv/Locate.srv"
  "srv/Stop.srv"
  "msg/RobotState.msg"
)

ament_package()
