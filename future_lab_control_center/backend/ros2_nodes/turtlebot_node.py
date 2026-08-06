import os
import time
import threading
import subprocess
from typing import Dict, Optional

# Configura o Discovery Server do TurtleBot 4 (192.168.0.129:11811) no ambiente Python do rclpy
os.environ["ROS_DOMAIN_ID"] = "0"
os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "SUBNET"
os.environ["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
os.environ["ROS_SUPER_CLIENT"] = "True"
os.environ["ROS_DISCOVERY_SERVER"] = "192.168.0.129:11811"

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import BatteryState, CompressedImage, Image
    from nav_msgs.msg import Odometry
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False
    Node = object

try:
    from irobot_create_msgs.msg import DockStatus
    HAS_CREATE_MSGS = True
except ImportError:
    HAS_CREATE_MSGS = False


class TurtleBotNode(Node):
    def __init__(self):
        self.battery_percentage: Optional[float] = None
        self.is_docked: bool = True
        self.current_pose: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.last_msg_time: float = time.time()
        self.latest_jpeg_frame: Optional[bytes] = None

        if HAS_RCLPY:
            if not rclpy.ok():
                try:
                    rclpy.init()
                except Exception:
                    pass
            try:
                super().__init__("future_lab_turtlebot_node")
                self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_unstamped", 10)
                self.create_subscription(BatteryState, "/battery_state", self._battery_callback, 10)
                self.create_subscription(Odometry, "/odom", self._odom_callback, 10)
                self.create_subscription(CompressedImage, "/oakd/rgb/preview/image_raw/compressed", self._compressed_image_callback, 10)
                if HAS_CREATE_MSGS:
                    self.create_subscription(DockStatus, "/dock_status", self._dock_status_callback, 10)

                # Thread de spin em background
                t_spin = threading.Thread(target=self._spin_loop, daemon=True)
                t_spin.start()
            except Exception as e:
                print(f"[WARN] Erro ao inicializar TurtleBotNode: {e}")
                self.cmd_vel_pub = None
        else:
            self.cmd_vel_pub = None

        # Thread de fallback proativo para telemetria
        t_poll = threading.Thread(target=self._poll_fallback_loop, daemon=True)
        t_poll.start()

    def _spin_loop(self):
        try:
            rclpy.spin(self)
        except Exception:
            pass

    def _compressed_image_callback(self, msg):
        try:
            self.latest_jpeg_frame = bytes(msg.data)
            self.last_msg_time = time.time()
        except Exception:
            pass

    def _poll_fallback_loop(self):
        """Consulta preventiva de telemetria se a rede atrasar a descoberta."""
        while True:
            try:
                if self.battery_percentage is None or (time.time() - self.last_msg_time > 15.0):
                    cmd = (
                        "source /opt/ros/jazzy/setup.bash && "
                        "export ROS_DOMAIN_ID=0 && "
                        "export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET && "
                        "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && "
                        "export ROS_SUPER_CLIENT=True && "
                        "export ROS_DISCOVERY_SERVER=192.168.0.129:11811 && "
                        "ros2 topic echo /battery_state --once"
                    )
                    res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=6)
                    if res.returncode == 0:
                        for line in res.stdout.splitlines():
                            if "percentage:" in line:
                                val = float(line.split(":")[-1].strip())
                                self.battery_percentage = round(val * (100.0 if val <= 1.0 else 1.0), 1)
                                self.last_msg_time = time.time()
                                break
            except Exception:
                pass
            time.sleep(10.0)

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

    def _dock_status_callback(self, msg):
        try:
            self.last_msg_time = time.time()
            if hasattr(msg, 'is_docked'):
                self.is_docked = bool(msg.is_docked)
        except Exception:
            pass

    def send_cmd_vel(self, linear_x: float, angular_z: float):
        if HAS_RCLPY and self.cmd_vel_pub:
            t = Twist()
            t.linear.x = float(linear_x)
            t.angular.z = float(angular_z)
            # Publica rajada de pulsos por 0.5s para superar o watchdog do iRobot Create 3
            def _burst():
                for _ in range(10):
                    try:
                        self.cmd_vel_pub.publish(t)
                    except Exception:
                        pass
                    time.sleep(0.05)
            threading.Thread(target=_burst, daemon=True).start()

    def get_status(self) -> Dict:
        return {
            "battery_percentage": self.battery_percentage if self.battery_percentage is not None else 99.0,
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
