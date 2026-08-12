import os
import time
import threading
import subprocess
from typing import Dict, Optional

os.environ["ROS_DOMAIN_ID"] = "0"
os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "SUBNET"
os.environ["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
os.environ["ROS_SUPER_CLIENT"] = "True"
os.environ["ROS_DISCOVERY_SERVER"] = "192.168.0.129:11811;"

JAZZY_ENV_CMD = (
    "source /opt/ros/jazzy/setup.bash && "
    "export ROS_DOMAIN_ID=0 && "
    "export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET && "
    "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && "
    "export FASTDDS_BUILTIN_TRANSPORTS=UDPv4 && "
    "export ROS_SUPER_CLIENT=True && "
    "export ROS_DISCOVERY_SERVER=\"192.168.0.129:11811;\" && "
)

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import BatteryState, CompressedImage, Image
    from nav_msgs.msg import Odometry
    from std_srvs.srv import Trigger
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False
    Node = object
    qos_profile_sensor_data = 10

try:
    from irobot_create_msgs.msg import DockStatus
    HAS_CREATE_MSGS = True
except ImportError:
    HAS_CREATE_MSGS = False


class TurtleBotNode(Node):
    def __init__(self):
        self.battery_percentage: Optional[float] = None
        self.is_docked: bool = False
        self.current_pose: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.last_msg_time: float = time.time()
        self.latest_jpeg_frame: Optional[bytes] = None

        self.start_delivery_cli = None
        self.start_failure_cli = None
        self.start_restock_cli = None
        self.stop_mission_cli = None

        if HAS_RCLPY:
            if not rclpy.ok():
                try:
                    rclpy.init()
                except Exception:
                    pass
            try:
                super().__init__("future_lab_turtlebot_node")
                self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_unstamped", 10)
                self.create_subscription(BatteryState, "/battery_state", self._battery_callback, qos_profile_sensor_data)
                self.create_subscription(Odometry, "/odom", self._odom_callback, qos_profile_sensor_data)
                self.create_subscription(CompressedImage, "/oakd/rgb/preview/image_raw/compressed", self._compressed_image_callback, 10)
                if HAS_CREATE_MSGS:
                    try:
                        self.create_subscription(DockStatus, "/dock_status", self._dock_status_callback, qos_profile_sensor_data)
                    except Exception as e:
                        print(f"[WARN TB4] Não foi possível se inscrever em /dock_status: {e}")

                self.start_delivery_cli = self.create_client(Trigger, "/start_delivery")
                self.start_failure_cli = self.create_client(Trigger, "/start_failure")
                self.start_restock_cli = self.create_client(Trigger, "/start_restock")
                self.stop_mission_cli = self.create_client(Trigger, "/stop_mission")

                # Thread de spin em background
                t_spin = threading.Thread(target=self._spin_loop, daemon=True)
                t_spin.start()
            except Exception as e:
                print(f"[WARN] Erro ao inicializar TurtleBotNode: {e}")
                self.cmd_vel_pub = None
        # Thread de fallback proativo para telemetria (Bateria e Dock Status)
        t_poll = threading.Thread(target=self._poll_fallback_loop, daemon=True)
        t_poll.start()

    def call_trigger_service(self, srv_name: str) -> bool:
        """Dispara um serviço Trigger do TurtleBot 4 (delivery, failure, restock, stop) via Subprocess CLI com ambiente Discovery Server."""
        try:
            cmd = JAZZY_ENV_CMD + f"ros2 service call /{srv_name} std_srvs/srv/Trigger '{{}}'"
            print(f"[INFO] 🚀 Disparando serviço ROS 2 '/{srv_name}' no TurtleBot 4...")
            subprocess.Popen(cmd, shell=True, executable="/bin/bash")
            return True
        except Exception as e:
            print(f"[WARN] Erro ao disparar serviço '/{srv_name}': {e}")
            return False

    def _spin_loop(self):
        try:
            rclpy.spin(self)
        except Exception as e:
            print(f"[WARN] TurtleBotNode spin finalizado: {e}")

    def _compressed_image_callback(self, msg):
        try:
            self.latest_jpeg_frame = bytes(msg.data)
            self.last_msg_time = time.time()
        except Exception:
            pass

    def _poll_fallback_loop(self):
        """Consulta preventiva de telemetria (bateria e docking) com Discovery Server e UDPv4 ativos."""
        while True:
            try:
                # 1. Leitura Real da Bateria & Status de Carregamento/Docking
                cmd_bat = JAZZY_ENV_CMD + "ros2 topic echo /battery_state --once --qos-reliability best_effort"
                res_bat = subprocess.run(cmd_bat, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=6)
                if res_bat.returncode == 0:
                    for line in res_bat.stdout.splitlines():
                        if "percentage:" in line:
                            val = float(line.split(":")[-1].strip())
                            self.battery_percentage = round(val * (100.0 if val <= 1.0 else 1.0), 1)
                            self.last_msg_time = time.time()
                        elif "power_supply_status:" in line:
                            try:
                                status_val = int(line.split(":")[-1].strip())
                                # 1: CHARGING, 4: FULL -> Docked | 2: DISCHARGING, 3: NOT_CHARGING -> Undocked
                                if status_val in (1, 4):
                                    self.is_docked = True
                                elif status_val in (2, 3):
                                    self.is_docked = False
                            except ValueError:
                                pass

                # 2. Leitura Real do Dock Status
                cmd_dock = JAZZY_ENV_CMD + "ros2 topic echo /dock_status --once --qos-reliability best_effort"
                res_dock = subprocess.run(cmd_dock, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=6)
                if res_dock.returncode == 0:
                    for line in res_dock.stdout.splitlines():
                        if "is_docked:" in line:
                            val_str = line.split(":")[-1].strip().lower()
                            self.is_docked = (val_str == "true")
                            self.last_msg_time = time.time()
                            break
            except Exception as e:
                pass
            time.sleep(3.0)

    def _battery_callback(self, msg):
        try:
            self.last_msg_time = time.time()
            if hasattr(msg, 'percentage'):
                self.battery_percentage = round(float(msg.percentage) * (100.0 if msg.percentage <= 1.0 else 1.0), 1)
            if hasattr(msg, 'power_supply_status'):
                status_val = int(msg.power_supply_status)
                if status_val in (1, 4):
                    self.is_docked = True
                elif status_val in (2, 3):
                    self.is_docked = False
        except Exception as e:
            print(f"[WARN TB4] Battery callback error: {e}")

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
                print(f"[DEBUG TB4] DockStatus callback: is_docked={msg.is_docked}")
                self.is_docked = bool(msg.is_docked)
        except Exception as e:
            print(f"[WARN TB4] DockStatus callback error: {e}")

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
        # Se a telemetria não foi capturada recentemente pelos callbacks (> 5s), realiza uma tentativa síncrona
        if self.battery_percentage is None or (time.time() - self.last_msg_time) > 5.0:
            try:
                cmd = JAZZY_ENV_CMD + "ros2 topic echo /battery_state --once"
                res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if "percentage:" in line:
                            val = float(line.split(":")[-1].strip())
                            self.battery_percentage = round(val * (100.0 if val <= 1.0 else 1.0), 1)
                            self.last_msg_time = time.time()
                        elif "power_supply_status:" in line:
                            try:
                                status_val = int(line.split(":")[-1].strip())
                                if status_val in (1, 4):
                                    self.is_docked = True
                                elif status_val in (2, 3):
                                    self.is_docked = False
                            except ValueError:
                                pass
            except Exception:
                pass

        return {
            "battery_percentage": self.battery_percentage if self.battery_percentage is not None else 50.0,
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
