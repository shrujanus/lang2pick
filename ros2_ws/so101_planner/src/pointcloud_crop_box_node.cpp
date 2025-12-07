#include <memory>
#include <string>
#include <vector>

#include <Eigen/Geometry>
#include <pcl/filters/crop_box.h>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl_conversions/pcl_conversions.h>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>

class PointcloudCropBoxNode : public rclcpp::Node
{
public:
  explicit PointcloudCropBoxNode(const rclcpp::NodeOptions& options)
    : rclcpp::Node("pointcloud_crop_box", options)
  {
    input_topic_ = declare_parameter<std::string>("input_topic", "/camera/depth/color/points");
    output_topic_ = declare_parameter<std::string>("output_topic", "/workspace/points");
    min_bounds_ = declare_parameter<std::vector<double>>("min_bounds", { -0.25, -0.25, 0.0 });
    max_bounds_ = declare_parameter<std::vector<double>>("max_bounds", { 0.25, 0.25, 0.4 });
    target_frame_ = declare_parameter<std::string>("target_frame", "");

    publisher_ = create_publisher<sensor_msgs::msg::PointCloud2>(output_topic_, rclcpp::SensorDataQoS());
    subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
        input_topic_, rclcpp::SensorDataQoS(),
        std::bind(&PointcloudCropBoxNode::cloudCallback, this, std::placeholders::_1));
  }

private:
  void cloudCallback(const sensor_msgs::msg::PointCloud2::SharedPtr msg)
  {
    pcl::PointCloud<pcl::PointXYZ> cloud;
    pcl::fromROSMsg(*msg, cloud);

    pcl::CropBox<pcl::PointXYZ> crop;
    crop.setInputCloud(cloud.makeShared());
    Eigen::Vector4f min_pt(min_bounds_.size() > 0 ? static_cast<float>(min_bounds_[0]) : -0.3f,
                           min_bounds_.size() > 1 ? static_cast<float>(min_bounds_[1]) : -0.3f,
                           min_bounds_.size() > 2 ? static_cast<float>(min_bounds_[2]) : 0.0f, 1.0f);
    Eigen::Vector4f max_pt(max_bounds_.size() > 0 ? static_cast<float>(max_bounds_[0]) : 0.3f,
                           max_bounds_.size() > 1 ? static_cast<float>(max_bounds_[1]) : 0.3f,
                           max_bounds_.size() > 2 ? static_cast<float>(max_bounds_[2]) : 0.5f, 1.0f);
    crop.setMin(min_pt);
    crop.setMax(max_pt);

    pcl::PointCloud<pcl::PointXYZ> filtered;
    crop.filter(filtered);

    sensor_msgs::msg::PointCloud2 output;
    pcl::toROSMsg(filtered, output);
    output.header = msg->header;
    if (!target_frame_.empty())
    {
      output.header.frame_id = target_frame_;
    }
    publisher_->publish(output);
  }

  std::string input_topic_;
  std::string output_topic_;
  std::string target_frame_;
  std::vector<double> min_bounds_;
  std::vector<double> max_bounds_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr publisher_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subscription_;
};

int main(int argc, char** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions options;
  options.automatically_declare_parameters_from_overrides(false);
  auto node = std::make_shared<PointcloudCropBoxNode>(options);
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
