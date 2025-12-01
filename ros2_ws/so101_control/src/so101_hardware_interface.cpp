#include "so101_control/so101_hardware_interface.hpp"

so101_control::so101_hardware_interface::so101_hardware_interface()
{
}

hardware_interface::CallbackReturn
so101_control::so101_hardware_interface::on_init(const hardware_interface::HardwareInfo& params)
{
  if (hardware_interface::SystemInterface::on_init(params) != hardware_interface::CallbackReturn::SUCCESS)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }

  // Finding usb_port and baud_rate from hardware parameters
  auto it = params.hardware_parameters.find("usb_port");
  if (it == params.hardware_parameters.end())
  {
    RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "USB port not specified in hardware parameters.");
    return hardware_interface::CallbackReturn::ERROR;
  }
  usb_port_ = it->second;
  auto baud_it = params.hardware_parameters.find("baud_rate");
  if (baud_it == params.hardware_parameters.end())
  {
    RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Baud rate not specified in hardware parameters.");
    return hardware_interface::CallbackReturn::ERROR;
  }
  baud_rate_ = std::stoi(baud_it->second);
  num_joints_ = params.joints.size();
  servos_.resize(num_joints_);
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Initializing hardware interface for %d joints.",
              num_joints_);

  auto control_mode_it = params.hardware_parameters.find("control_mode");
  if (control_mode_it == params.hardware_parameters.end())
  {
    RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Control mode not specified in hardware parameters.");
    return hardware_interface::CallbackReturn::ERROR;
  }
  control_mode_ = std::stoi(control_mode_it->second);

  num_joints_ = params.joints.size();
  std::unordered_set<std::string> joint_names, state_interface_names, command_interface_names;

  for (int i = 0; i < num_joints_; ++i)
  {
    if (joint_names.find(params.joints[i].name) != joint_names.end())
    {
      RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Joint name %s is not unique.",
                   params.joints[i].name.c_str());
      return hardware_interface::CallbackReturn::ERROR;
    }

    // Configuring State Interfaces
    if (params.joints[i].state_interfaces.size() < 3)
    {
      RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Joint %s does not have 5 state interfaces.",
                   params.joints[i].name.c_str());
      return hardware_interface::CallbackReturn::ERROR;
    }
    state_interface_names.clear();
    for (const auto& state_interface : params.joints[i].state_interfaces)
    {
      if (state_interface_names.find(state_interface.name) != state_interface_names.end() ||
          (state_interface.name != "position" && state_interface.name != "velocity" &&
           state_interface.name != "effort" && state_interface.name != "temperature" &&
           state_interface.name != "voltage"))
      {
        RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"),
                     "Joint %s has duplicate/unknown state interface %s.", params.joints[i].name.c_str(),
                     state_interface.name.c_str());
        return hardware_interface::CallbackReturn::ERROR;
      }

      state_interface_names.insert(state_interface.name);
    }

    // Configuring Command Interfaces
    if (params.joints[i].command_interfaces.size() < 1)
    {
      RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Joint %s does not have 2 command interfaces.",
                   params.joints[i].name.c_str());
      return hardware_interface::CallbackReturn::ERROR;
    }
    command_interface_names.clear();
    for (const auto& command_interface : params.joints[i].command_interfaces)
    {
      if (command_interface_names.find(command_interface.name) != command_interface_names.end())
      {
        RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Joint %s has duplicate command interface %s.",
                     params.joints[i].name.c_str(), command_interface.name.c_str());
        return hardware_interface::CallbackReturn::ERROR;
      }
      command_interface_names.insert(command_interface.name);
    }

    // Configuring Servo Parameters
    auto id_it = params.joints[i].parameters.find("id");
    if (id_it == params.joints[i].parameters.end())
    {
      RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Joint %s is missing parameter 'id'.",
                   params.joints[i].name.c_str());
      return hardware_interface::CallbackReturn::ERROR;
    }
    int id = std::stoi(params.joints[i].parameters.at("id"));
    servos_[i] = so101_control::Servo(id);

    auto offset_it = params.joints[i].parameters.find("position_offset");
    if (offset_it != params.joints[i].parameters.end())
    {
      servos_[i].position_offset = std::stod(offset_it->second);
    }
    servos_[i].cmd_id = params.joints[i].parameters.at("type") == "position" ? 0.0 : 1.0;

    auto min_range_it = params.joints[i].parameters.find("min_range");
    if (min_range_it != params.joints[i].parameters.end())
    {
      servos_[i].min_range = std::stoi(min_range_it->second);
    }

    auto max_range_it = params.joints[i].parameters.find("max_range");
    if (max_range_it != params.joints[i].parameters.end())
    {
      servos_[i].max_range = std::stoi(max_range_it->second);
    }

    auto min_angle_it = params.joints[i].parameters.find("min_angle");
    if (min_angle_it != params.joints[i].parameters.end())
    {
      servos_[i].min_angle = std::stod(min_angle_it->second);
    }

    auto max_angle_it = params.joints[i].parameters.find("max_angle");
    if (max_angle_it != params.joints[i].parameters.end())
    {
      servos_[i].max_angle = std::stod(max_angle_it->second);
    }
  }
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn
so101_control::so101_hardware_interface::on_configure(const rclcpp_lifecycle::State& /*previous_state*/)
{
  if (!motor_driver_.begin(baud_rate_, usb_port_.c_str()))
  {
    RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Failed to open motor driver on port: %s",
                 usb_port_.c_str());
    return hardware_interface::CallbackReturn::ERROR;
  }
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Successfully connected to motor driver on port: %s",
              usb_port_.c_str());

  // Ping each servo to ensure they are connected
  for (int i = 0; i < num_joints_; ++i)
  {
    if (motor_driver_.Ping(servos_[i].id) == -1)
    {
      RCLCPP_FATAL(rclcpp::get_logger("so101_hardware_interface"), "Failed to ping motor ID %d.", servos_[i].id);
      return hardware_interface::CallbackReturn::ERROR;
    }
  }
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Successfully pinged all motor IDs.");

  // setting up each servo
  for (int i = 0; i < num_joints_; ++i)
  {
    motor_driver_.Mode(servos_[i].id, control_mode_);  // 0=Servo, 1=Closed_loop, 2=Open_loop
    motor_driver_.EnableTorque(servos_[i].id, 1);
  }
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Set to control mode %d", control_mode_);
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn
so101_control::so101_hardware_interface::on_activate(const rclcpp_lifecycle::State& /*previous_state*/)
{
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Activating hardware interface for %d joints.",
              num_joints_);

  for (int i = 0; i < num_joints_; i++)
  {
    auto servo = servos_[i];
    int id = servos_[i].id;

    RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"),
                "ID: %d, min_range: %d, max_range: %d, min_angle: %f, max_angle: %f", id, servo.min_range,
                servo.max_range, servo.min_angle, servo.max_angle);
  }

  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn
so101_control::so101_hardware_interface::on_cleanup(const rclcpp_lifecycle::State& /*previous_state*/)
{
  motor_driver_.end();
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Motor driver connection closed.");
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn
so101_control::so101_hardware_interface::on_deactivate(const rclcpp_lifecycle::State& /*previous_state*/)
{
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Deactivating hardware interface for %d joints.",
              num_joints_);
  for (int i = 0; i < num_joints_; ++i)
  {
    motor_driver_.EnableTorque(servos_[i].id, 1);
  }
  // this->write(rclcpp::Time(), rclcpp::Duration(0, 0));
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn
so101_control::so101_hardware_interface::on_shutdown(const rclcpp_lifecycle::State& /*previous_state*/)
{
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Shutting down...");
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn
so101_control::so101_hardware_interface::on_error(const rclcpp_lifecycle::State& /*previous_state*/)
{
  RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "Error...");
  return hardware_interface::CallbackReturn::SUCCESS;
}
std::vector<hardware_interface::StateInterface> so101_control::so101_hardware_interface::export_state_interfaces()
{
  std::vector<hardware_interface::StateInterface> state_interfaces;
  for (int i = 0; i < num_joints_; ++i)
  {
    state_interfaces.emplace_back(
        hardware_interface::StateInterface(info_.joints[i].name, "position", &servos_[i].position_state));
    state_interfaces.emplace_back(
        hardware_interface::StateInterface(info_.joints[i].name, "velocity", &servos_[i].velocity_state));
    state_interfaces.emplace_back(
        hardware_interface::StateInterface(info_.joints[i].name, "effort", &servos_[i].torque_state));
    // state_interfaces.emplace_back(
    //     hardware_interface::StateInterface(info_.joints[i].name, "temperature", &servos_[i].temperature_state));
    // state_interfaces.emplace_back(
    //     hardware_interface::StateInterface(info_.joints[i].name, "voltage", &servos_[i].voltage_state));
  }
  return state_interfaces;
}

std::vector<hardware_interface::CommandInterface> so101_control::so101_hardware_interface::export_command_interfaces()
{
  std::vector<hardware_interface::CommandInterface> command_interfaces;
  for (int i = 0; i < num_joints_; ++i)
  {
    command_interfaces.emplace_back(
        hardware_interface::CommandInterface(info_.joints[i].name, "position", &servos_[i].cmd_position));
  }
  return command_interfaces;
}

hardware_interface::return_type so101_control::so101_hardware_interface::read(const rclcpp::Time& /*time*/,
                                                                              const rclcpp::Duration& /*period*/)
{
  for (int i = 0; i < num_joints_; ++i)
  {
    if (update_hardware_status(i) == hardware_interface::CallbackReturn::ERROR)
    {
      RCLCPP_ERROR(rclcpp::get_logger("so101_hardware_interface"),
                   "Failed to get feedback from motor ID %d during read.", servos_[i].id);
      return hardware_interface::return_type::ERROR;
    }
  }
  return hardware_interface::return_type::OK;
}

hardware_interface::return_type so101_control::so101_hardware_interface::write(const rclcpp::Time& /*time*/,
                                                                               const rclcpp::Duration& /*period*/)
{
  u8 ids[num_joints_];
  s16 position[num_joints_];
  u16 speed[num_joints_];
  u8 acceleration[num_joints_];
  for (int i = 0; i < num_joints_; ++i)
  {
    int id = servos_[i].id;
    ids[i] = static_cast<u8>(id);
    position[i] = rad_to_ticks_(servos_[i].cmd_position, i);
    speed[i] = 4500;
    acceleration[i] = 255;
  }
  motor_driver_.SyncWritePosEx(ids, num_joints_, position, speed, acceleration);
  return hardware_interface::return_type::OK;
}

hardware_interface::CallbackReturn so101_control::so101_hardware_interface::update_hardware_status(int index)

{
  int id = servos_[index].id;

  int raw_pos = motor_driver_.ReadPos(id);
  int raw_vel = motor_driver_.ReadSpeed(id);

  servos_[index].position_state = ticks_to_rad_(raw_pos, index);

  servos_[index].velocity_state = ticks_to_rad_(raw_vel, index);

  servos_[index].torque_state = motor_driver_.ReadLoad(id);
  servos_[index].voltage_state = motor_driver_.ReadVoltage(id);
  servos_[index].temperature_state = motor_driver_.ReadTemper(id);

  // RCLCPP_INFO(rclcpp::get_logger("so101_hardware_interface"), "ID: 6 raw_pos: %d, joint_pos: %f",
  //             motor_driver_.ReadPos(6),servos_[5].position_state);

  return hardware_interface::CallbackReturn::SUCCESS;
}

double so101_control::so101_hardware_interface::ticks_to_rad_(double ticks, int servo_index)
{
  const auto& servo = servos_[servo_index];
  int zeroed = static_cast<int>(ticks);

  if (zeroed < servo.min_range)
    zeroed = servo.min_range;
  if (zeroed > servo.max_range)
    zeroed = servo.max_range;

  double ratio = static_cast<double>(zeroed - servo.min_range) / (servo.max_range - servo.min_range);
  return servo.min_angle + ratio * (servo.max_angle - servo.min_angle);
}

int so101_control::so101_hardware_interface::rad_to_ticks_(double rad, int servo_index)
{
  const auto& servo = servos_[servo_index];
  // double cmd = std::clamp(rad,servo.min_angle,servo.max_angle);

  double ratio = (rad - servo.min_angle) / (servo.max_angle - servo.min_angle);

  return static_cast<int>(servo.min_range + ratio * (servo.max_range - servo.min_range));
}

PLUGINLIB_EXPORT_CLASS(so101_control::so101_hardware_interface, hardware_interface::SystemInterface)