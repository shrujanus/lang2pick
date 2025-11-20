#ifndef SO101_HARDWARE_INTERFACE_HPP
#define SO101_HARDWARE_INTERFACE_HPP

#include <cmath>
#include <string>
#include <vector>
#include <algorithm>

#include "SCServo.h"
#include "hardware_interface/handle.hpp"
#include "hardware_interface/hardware_info.hpp"
#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_interface_return_values.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "rclcpp/macros.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/node_interfaces/lifecycle_node_interface.hpp"
#include "rclcpp_lifecycle/state.hpp"

using hardware_interface::CallbackReturn;

namespace so101_control
{

struct Servo
{
  Servo() = default;
  Servo(int servo_id) : id(servo_id)
  {
  }
  int id{ 0 };
  double position_offset{ 0.0 };  // homing_offset
  int min_range{ 0 };
  int max_range{ 0 };
  double min_angle{ -6.28319 };
  double max_angle{ 6.28319 };

  int cmd_id{ 0 };  // 0 = position, 1 = velocity
  double cmd_position{ 0 };

  double position_state{ 0.0 };
  double velocity_state{ 0.0 };
  double torque_state{ 0.0 };
  double temperature_state{ 0.0 };
  double voltage_state{ 0.0 };
};

class so101_hardware_interface final : public hardware_interface::SystemInterface
{
private:
  SMS_STS motor_driver_;
  std::string usb_port_ = "/dev/ttyUSB0";
  std::vector<Servo> servos_;
  int baud_rate_ = 115200;
  int num_joints_ = 6;
  int steps_per_rev_ = 4096;
  CallbackReturn update_hardware_status(int i);
  int control_mode_ = 1;  // 0=Servo, 1=Closed_loop, 2=Open_loop
  double ticks_to_rad_(double ticks, int servo_index);
  int rad_to_ticks_(double rad, int servo_index);

public:
  so101_hardware_interface();

  // Lifecycle methods
  CallbackReturn on_configure(const rclcpp_lifecycle::State& previous_state) override;
  CallbackReturn on_activate(const rclcpp_lifecycle::State& previous_state) override;
  CallbackReturn on_deactivate(const rclcpp_lifecycle::State& previous_state) override;
  CallbackReturn on_cleanup(const rclcpp_lifecycle::State& previous_state) override;
  CallbackReturn on_shutdown(const rclcpp_lifecycle::State& previous_state) override;
  CallbackReturn on_error(const rclcpp_lifecycle::State& previous_state) override;
  // Export interfaces
  CallbackReturn on_init(const hardware_interface::HardwareInfo& params) override;
  std::vector<hardware_interface::StateInterface> export_state_interfaces() override;
  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override;

  // Read/Write methods
  hardware_interface::return_type read(const rclcpp::Time& time, const rclcpp::Duration& period) override;
  hardware_interface::return_type write(const rclcpp::Time& time, const rclcpp::Duration& period) override;
};

}  // namespace so101_control

#endif