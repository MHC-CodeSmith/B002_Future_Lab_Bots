# ============================================================
# turtlebot_node.py — Nó ROS 2 de Ponte com o TurtleBot 4 (AMR)
# ============================================================
import time
from typing import Dict, Optional

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import BatteryState
    from nav_msgs.msg import Odometry
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False
    Node = object

class TurtleBotNode(Node):
    def __init__(self):
        if HAS_RCLPY:
            super().__init__("future_lab_turtlebot_node")
            self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)
            self.create_subscription(BatteryState, "/battery_state", self._battery_callback, 10)
            self.create_subscription(Odometry, "/odom", self._odom_callback, 10)
        else:
            self.cmd_vel_pub = None

        self.battery_percentage: float = 100.0
        self.is_docked: bool = True
        self.current_pose: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.last_msg_time: float = time.time()

    def _battery_callback(self, msg):
        try:
            self.last_msg_time = time.time()
            if hasattr(msg, 'percentage'):
                self.battery_percentage = round(float(msg.percentage) * (100.0 if msg.percentage <= 1.0 else 1.0), 1)
        except Exception:
            pass

    def _odom_callback(self, msg):
        try:
            self.last_msg_time = time.time()
            pos = msg.pose.pose.position
            self.current_pose["x"] = round(float(pos.x), 2)
            self.current_pose["y"] = round(float(pos.y), 2)
        except Exception:
            pass

    def send_cmd_vel(self, linear_x: float, angular_z: float):
        if HAS_RCLPY and self.cmd_vel_pub:
            t = Twist()
            t.linear.x = float(linear_x)
            t.angular.z = float(angular_z)
            self.cmd_vel_pub.publish(t)

    def get_status(self) -> Dict:
        return {
            "battery_percentage": self.battery_percentage,
            "is_docked": self.is_docked,
            "current_pose": self.current_pose,
            "status": "ready"
        }

_tb_node: Optional[TurtleBotNode] = None

def get_turtlebot_node() -> TurtleBotNode:
    global _tb_node
    if _tb_node is None:
        _tb_node = TurtleBotNode()
    return _tb_node
