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
    "source /home/future-lab/B002_Future_Lab_Bots/turtlebot4_jazzy/setup.bash && "
    "export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET && "
    "export ROS_SUPER_CLIENT=True && "
    "export ROS_DISCOVERY_SERVER='192.168.0.129:11811;' && "
    "export DISPLAY=:0 && "
)

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, qos_profile_sensor_data
    from geometry_msgs.msg import Twist, TwistStamped
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


TELEMETRY_TTL = 5.0   # s sem mensagem da BASE = telemetria inválida
FRAME_TTL = 3.0       # s sem frame da OAK-D = câmera sem sinal


class TurtleBotNode(Node):
    def __init__(self):
        self.battery_percentage: Optional[float] = None
        self.battery_current: Optional[float] = None
        self.is_docked: bool = False
        self.current_pose: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.last_telemetry_time: float = 0.0
        self.last_frame_time: float = 0.0
        self.latest_jpeg_frame: Optional[bytes] = None

        self._dock_raw_last: Optional[bool] = None
        self._dock_confirm_count: int = 0

        self.cmd_vel_pub = None
        self.cmd_vel_stamped_pub = None
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
                self.cmd_vel_stamped_pub = self.create_publisher(TwistStamped, "/cmd_vel", 10)
                self.create_subscription(BatteryState, "/battery_state", self._battery_callback, qos_profile_sensor_data)
                self.create_subscription(Odometry, "/odom", self._odom_callback, qos_profile_sensor_data)
                self.create_subscription(Image, "/oakd/rgb/preview/image_raw", self._raw_image_callback, qos_profile_sensor_data)
                self.create_subscription(CompressedImage, "/oakd/rgb/preview/image_raw/compressed", self._compressed_image_callback, qos_profile_sensor_data)
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
                print(f"[WARN TB4] Erro ao inicializar nó rclpy: {e}")

        # Thread de polling de fallback para bateria/docking via CLI caso rclpy perca conectividade
        t_poll = threading.Thread(target=self._poll_fallback_loop, daemon=True)
        t_poll.start()

    def _spin_loop(self):
        if HAS_RCLPY:
            try:
                from rclpy.executors import SingleThreadedExecutor
                executor = SingleThreadedExecutor()
                executor.add_node(self)
                executor.spin()
            except Exception as e:
                print(f"[WARN TB4] Spin loop finalizado: {e}")

    def _compressed_image_callback(self, msg):
        try:
            self.latest_jpeg_frame = bytes(msg.data)
            self.last_frame_time = time.time()
        except Exception:
            pass

    def _raw_image_callback(self, msg):
        try:
            import cv2
            import numpy as np
            height = msg.height
            width = msg.width
            if height > 0 and width > 0:
                channels = 3
                img = np.frombuffer(msg.data, dtype=np.uint8).reshape((height, width, channels))
                if "rgb" in msg.encoding.lower():
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                success, encoded_img = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if success:
                    self.latest_jpeg_frame = encoded_img.tobytes()
                    self.last_frame_time = time.time()
        except Exception:
            pass

    def _set_docked_debounced(self, value: bool):
        """Só altera is_docked após duas leituras consecutivas idênticas."""
        if value == self._dock_raw_last:
            self._dock_confirm_count += 1
        else:
            self._dock_raw_last = value
            self._dock_confirm_count = 1
        if self._dock_confirm_count >= 2 and self.is_docked != value:
            print(f"[TB4] is_docked {self.is_docked} -> {value}")
            self.is_docked = value

    def _poll_fallback_loop(self):
        """Consulta preventiva de telemetria (bateria e docking) com Discovery Server ativo."""
        while True:
            if not self.telemetry_fresh():
                try:
                    # 1. Leitura Real da Bateria
                    cmd_bat = JAZZY_ENV_CMD + "ros2 topic echo /battery_state --once"
                    res_bat = subprocess.run(cmd_bat, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=3)
                    if res_bat.returncode == 0:
                        got_bat = False
                        for line in res_bat.stdout.splitlines():
                            if "percentage:" in line:
                                val = float(line.split(":")[-1].strip())
                                self.battery_percentage = round(val * (100.0 if val <= 1.0 else 1.0), 1)
                                got_bat = True
                            elif "current:" in line:
                                self.battery_current = float(line.split(":")[-1].strip())
                                got_bat = True
                        if got_bat:
                            self.last_telemetry_time = time.time()

                    # 2. Leitura Real do Dock Status
                    cmd_dock = JAZZY_ENV_CMD + "ros2 topic echo /dock_status --once"
                    res_dock = subprocess.run(cmd_dock, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=3)
                    if res_dock.returncode == 0:
                        for line in res_dock.stdout.splitlines():
                            if "is_docked:" in line:
                                val_str = line.split(":")[-1].strip().lower()
                                self._set_docked_debounced(val_str == "true")
                                self.last_telemetry_time = time.time()
                                break
                except Exception:
                    pass
            time.sleep(2.0)

    def set_dock_override(self, is_docked: bool, duration_sec: float = 5.0):
        self.is_docked = is_docked

    def clear_dock_override(self):
        pass

    def clear_undock_override(self):
        pass

    def force_undock_override(self, duration_sec: float = 5.0):
        self.is_docked = False

    def _battery_callback(self, msg):
        try:
            if hasattr(msg, 'percentage'):
                self.battery_percentage = round(float(msg.percentage) * (100.0 if msg.percentage <= 1.0 else 1.0), 1)
            if hasattr(msg, 'current'):
                self.battery_current = float(msg.current)
            self.last_telemetry_time = time.time()
        except Exception as e:
            print(f"[WARN TB4] Battery callback error: {e}")

    def _odom_callback(self, msg):
        try:
            pos = msg.pose.pose.position
            self.current_pose["x"] = round(float(pos.x), 2)
            self.current_pose["y"] = round(float(pos.y), 2)
            self.last_telemetry_time = time.time()
        except Exception:
            pass

    def _dock_status_callback(self, msg):
        try:
            if hasattr(msg, 'is_docked'):
                self._set_docked_debounced(bool(msg.is_docked))
                self.last_telemetry_time = time.time()
        except Exception as e:
            print(f"[WARN TB4] DockStatus callback error: {e}")

    def call_trigger_service(self, srv_name: str, timeout_sec: float = 2.0):
        """Chama um serviço Trigger do mission_manager e devolve (sucesso, mensagem) reais.
        Usa os clientes rclpy criados no __init__ em vez de subprocess fire-and-forget,
        para que o dashboard saiba de fato se a missão foi aceita."""
        cli_map = {
            "start_delivery": self.start_delivery_cli,
            "start_failure": self.start_failure_cli,
            "start_restock": self.start_restock_cli,
            "stop_mission": self.stop_mission_cli,
        }
        cli = cli_map.get(srv_name)
        if cli is None:
            return False, f"Serviço '/{srv_name}' não tem cliente registrado no backend."
        if not cli.wait_for_service(timeout_sec=timeout_sec):
            return False, (f"Serviço '/{srv_name}' indisponível — o Mission Manager não está "
                           f"rodando. Use o botão 'Iniciar Mission Manager' no painel.")
        try:
            fut = cli.call_async(Trigger.Request())
            t0 = time.time()
            while not fut.done() and (time.time() - t0) < (timeout_sec + 3.0):
                time.sleep(0.02)
            if not fut.done():
                return False, f"Timeout aguardando resposta de '/{srv_name}'."
            res = fut.result()
            return bool(res.success), (res.message or "")
        except Exception as e:
            return False, f"Erro ao chamar '/{srv_name}': {e}"

    def send_cmd_vel(self, linear_x: float, angular_z: float):
        if HAS_RCLPY and self.cmd_vel_pub:
            t = Twist()
            t.linear.x = float(linear_x)
            t.angular.z = float(angular_z)

            ts = TwistStamped()
            ts.header.frame_id = "base_link"
            ts.twist = t

            def _burst():
                for _ in range(10):
                    try:
                        self.cmd_vel_pub.publish(t)
                        if hasattr(self, 'cmd_vel_stamped_pub') and self.cmd_vel_stamped_pub:
                            ts.header.stamp = self.get_clock().now().to_msg()
                            self.cmd_vel_stamped_pub.publish(ts)
                    except Exception:
                        pass
                    time.sleep(0.05)
            threading.Thread(target=_burst, daemon=True).start()

    def telemetry_fresh(self) -> bool:
        return (time.time() - self.last_telemetry_time) < TELEMETRY_TTL

    def get_status(self) -> Dict:
        # Se a telemetria não foi capturada recentemente pelos callbacks (> 5s), realiza uma tentativa síncrona
        if not self.telemetry_fresh():
            try:
                cmd = JAZZY_ENV_CMD + "ros2 topic echo /battery_state --once"
                res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    got_bat = False
                    for line in res.stdout.splitlines():
                        if "percentage:" in line:
                            val = float(line.split(":")[-1].strip())
                            self.battery_percentage = round(val * (100.0 if val <= 1.0 else 1.0), 1)
                            got_bat = True
                        elif "current:" in line:
                            self.battery_current = float(line.split(":")[-1].strip())
                            got_bat = True
                    if got_bat:
                        self.last_telemetry_time = time.time()
            except Exception:
                pass

            try:
                cmd_d = JAZZY_ENV_CMD + "ros2 topic echo /dock_status --once"
                res_d = subprocess.run(cmd_d, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=2)
                if res_d.returncode == 0:
                    for line in res_d.stdout.splitlines():
                        if "is_docked:" in line:
                            val_str = line.split(":")[-1].strip().lower()
                            self._set_docked_debounced(val_str == "true")
                            self.last_telemetry_time = time.time()
                            break
            except Exception:
                pass

        fresh = self.telemetry_fresh()
        age = None if self.last_telemetry_time == 0.0 else round(time.time() - self.last_telemetry_time, 1)
        charging = None
        if fresh and self.battery_current is not None:
            charging = self.battery_current > 0.05

        return {
            "telemetry_ok": fresh,
            "telemetry_age_s": age,
            "status": "ready" if fresh else "no_telemetry",
            "battery_percentage": self.battery_percentage if fresh else None,
            "battery_current": round(self.battery_current, 3) if (fresh and self.battery_current is not None) else None,
            "charging": charging,
            "is_docked": self.is_docked if fresh else None,
            "current_pose": self.current_pose if fresh else None,
            "oakd_streaming": bool(self.latest_jpeg_frame and (time.time() - self.last_frame_time) < FRAME_TTL),
        }

_tb_node: Optional[TurtleBotNode] = None

def get_turtlebot_node() -> TurtleBotNode:
    global _tb_node
    if _tb_node is None:
        _tb_node = TurtleBotNode()
    return _tb_node
