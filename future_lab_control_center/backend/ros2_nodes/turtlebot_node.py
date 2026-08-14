import os
import time
import math
import threading
import subprocess
from typing import Dict, Optional

os.environ["ROS_DOMAIN_ID"] = "0"
os.environ["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "SUBNET"
os.environ["ROS_SUPER_CLIENT"] = "True"
os.environ["ROS_DISCOVERY_SERVER"] = "192.168.0.129:11811;"

JAZZY_ENV_CMD = (
    "source /opt/ros/jazzy/setup.bash && "
    "source /home/future-lab/B002_Future_Lab_Bots/turtlebot4_jazzy/setup.bash && "
    "export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET && "
    "export ROS_SUPER_CLIENT=True && "
    "export ROS_DISCOVERY_SERVER='192.168.0.129:11811;' && "
    "export DISPLAY=:0 && "
)

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.qos import (
        QoSProfile,
        QoSReliabilityPolicy,
        QoSDurabilityPolicy,
        qos_profile_sensor_data,
    )
    from geometry_msgs.msg import Twist, TwistStamped, PoseWithCovarianceStamped
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

try:
    from nav2_msgs.action import NavigateToPose
    from rclpy.action import ActionClient
    HAS_NAV2_ACTION = True
except ImportError:
    HAS_NAV2_ACTION = False


TELEMETRY_TTL = 5.0   # s sem mensagem da BASE = telemetria inválida
FRAME_TTL = 3.0       # s sem frame da OAK-D = câmera sem sinal
AMCL_TTL = 120.0      # o AMCL so publica quando atualiza; parado, fica em silencio
COV_XY_MAX = 0.05      # m² (em movimento)
COV_YAW_MAX = 0.06     # rad² (em movimento)
COV_XY_MAX_DOCK = 0.09 # m² (~30 cm de sigma; estado docado)
COV_YAW_MAX_DOCK = 0.12 # rad² (~20 graus de sigma; estado docado)


class TurtleBotNode(Node if HAS_RCLPY else object):
    def __init__(self):
        self.battery_percentage: Optional[float] = None
        self.battery_current: Optional[float] = None
        self.is_docked: bool = False
        self.current_pose: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.amcl_pose: Optional[Dict[str, float]] = None
        self.amcl_cov: Optional[Dict[str, float]] = None
        self.last_amcl_time: float = 0.0
        self.last_telemetry_time: float = 0.0
        self.last_frame_time: float = 0.0
        self._last_compressed_time: float = 0.0
        self.latest_jpeg_frame: Optional[bytes] = None

        self._dock_raw_last: Optional[bool] = None
        self._dock_confirm_count: int = 0

        self.cmd_vel_pub = None
        self.cmd_vel_stamped_pub = None
        self.initialpose_pub = None
        self.start_delivery_cli = None
        self.start_failure_cli = None
        self.start_restock_cli = None
        self.stop_mission_cli = None
        self.nav_action_client = None

        if HAS_RCLPY:
            if not rclpy.ok():
                try:
                    rclpy.init()
                except Exception:
                    pass
            try:
                super().__init__("future_lab_turtlebot_node")

                # Telemetria e imagens: serializadas entre si (MutuallyExclusiveCallbackGroup)
                self._cb_sub = MutuallyExclusiveCallbackGroup()
                # Clientes de serviço e action: não mutam estado e respondem mesmo com decodificação de imagem na outra thread
                self._cb_cli = ReentrantCallbackGroup()

                try:
                    self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_unstamped", 10)
                    self.cmd_vel_stamped_pub = self.create_publisher(TwistStamped, "/cmd_vel", 10)
                    self.initialpose_pub = self.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
                except Exception as e:
                    print(f"[WARN TB4] Erro ao criar publishers: {e}")

                if HAS_NAV2_ACTION:
                    try:
                        self.nav_action_client = ActionClient(self, NavigateToPose, "/navigate_to_pose", callback_group=self._cb_cli)
                    except Exception as e:
                        print(f"[WARN TB4] Erro ao criar ActionClient /navigate_to_pose: {e}")

                try:
                    self.create_subscription(BatteryState, "/battery_state", self._battery_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                except Exception as e:
                    print(f"[WARN TB4] Erro ao assinar /battery_state: {e}")

                try:
                    self.create_subscription(Odometry, "/odom", self._odom_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                except Exception as e:
                    print(f"[WARN TB4] Erro ao assinar /odom: {e}")

                try:
                    qos_latched = QoSProfile(
                        depth=1,
                        reliability=QoSReliabilityPolicy.RELIABLE,
                        durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                    )
                    self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self._amcl_callback, qos_latched, callback_group=self._cb_sub)
                except Exception as e:
                    print(f"[WARN TB4] Erro ao assinar /amcl_pose: {e}")

                try:
                    self.create_subscription(CompressedImage, "/oakd/rgb/preview/image_raw/compressed", self._compressed_image_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                except Exception as e:
                    print(f"[WARN TB4] Erro ao assinar topicos OAK-D: {e}")

                if HAS_CREATE_MSGS and hasattr(DockStatus, '_TYPE_SUPPORT'):
                    try:
                        self.create_subscription(DockStatus, "/dock_status", self._dock_status_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                    except Exception as e:
                        print(f"[WARN TB4] Não foi possível se inscrever em /dock_status: {e}")

                try:
                    self.start_delivery_cli = self.create_client(Trigger, "/start_delivery", callback_group=self._cb_cli)
                    self.start_failure_cli = self.create_client(Trigger, "/start_failure", callback_group=self._cb_cli)
                    self.start_restock_cli = self.create_client(Trigger, "/start_restock", callback_group=self._cb_cli)
                    self.stop_mission_cli = self.create_client(Trigger, "/stop_mission", callback_group=self._cb_cli)
                except Exception as e:
                    print(f"[WARN TB4] Erro ao criar clientes de missao: {e}")

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
                executor = MultiThreadedExecutor(num_threads=4)
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
        """Loop de monitoramento passivo de telemetria."""
        while True:
            time.sleep(5.0)

    def set_dock_override(self, is_docked: bool, duration_sec: float = 5.0):
        pass

    def clear_dock_override(self):
        pass

    def clear_undock_override(self):
        pass

    def force_undock_override(self, duration_sec: float = 5.0):
        pass

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
            ori = msg.pose.pose.orientation
            self.current_pose["x"] = round(float(pos.x), 2)
            self.current_pose["y"] = round(float(pos.y), 2)

            siny_cosp = 2.0 * (float(ori.w) * float(ori.z) + float(ori.x) * float(ori.y))
            cosy_cosp = 1.0 - 2.0 * (float(ori.y) * float(ori.y) + float(ori.z) * float(ori.z))
            self.current_pose["yaw"] = round(math.atan2(siny_cosp, cosy_cosp), 3)

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

    def _amcl_callback(self, msg):
        try:
            p = msg.pose.pose.position
            q = msg.pose.pose.orientation
            yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                             1.0 - 2.0 * (q.y * q.y + q.z * q.z))
            self.amcl_pose = {"x": round(float(p.x), 4),
                              "y": round(float(p.y), 4),
                              "yaw": round(float(yaw), 4)}
            cov = list(msg.pose.covariance)
            self.amcl_cov = {"x": round(float(cov[0]), 5),
                             "y": round(float(cov[7]), 5),
                             "yaw": round(float(cov[35]), 5)}
            self.last_amcl_time = time.time()
        except Exception as e:
            print(f"[WARN TB4] AMCL callback error: {e}")

    def get_amcl(self) -> Dict:
        if self.amcl_pose is None:
            return {"amcl_ok": False, "converged": False, "pose": None,
                    "covariance": None, "age_s": None,
                    "motivo": "nenhuma mensagem recebida em /amcl_pose"}
        idade = round(time.time() - self.last_amcl_time, 1)
        fresh = bool(idade < AMCL_TTL)
        c = self.amcl_cov or {"x": 1.0, "y": 1.0, "yaw": 1.0}
        converged = bool(fresh and (c["x"] < COV_XY_MAX and c["y"] < COV_XY_MAX
                                    and c["yaw"] < COV_YAW_MAX))
        return {"amcl_ok": fresh, "converged": converged, "pose": self.amcl_pose,
                "covariance": c, "age_s": idade,
                "motivo": "" if fresh else f"ultima leitura ha {idade}s"}

    def call_trigger_service(self, srv_name: str, descoberta_sec: float = 2.0, resposta_sec: float = 10.0):
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
        if not cli.wait_for_service(timeout_sec=descoberta_sec):
            return False, (f"Serviço '/{srv_name}' indisponível — o Mission Manager não está "
                           f"rodando. Use o botão 'Iniciar Mission Manager'.")
        try:
            fut = cli.call_async(Trigger.Request())
            t0 = time.time()
            while not fut.done() and (time.time() - t0) < resposta_sec:
                time.sleep(0.02)
            if not fut.done():
                return False, (f"Serviço '/{srv_name}' foi encontrado no grafo mas não "
                               f"respondeu em {resposta_sec}s. Isso indica caminho de dados "
                               f"bloqueado ou executor do backend saturado, não Mission Manager ausente.")
            res = fut.result()
            return bool(res.success), (res.message or "")
        except Exception as e:
            return False, f"Erro ao chamar '/{srv_name}': {e}"

    def cancel_all_nav_goals(self, timeout_sec: float = 2.0) -> tuple:
        """Cancela todas as metas ativas da action /navigate_to_pose via ActionClient.
        Retorna (sucesso: bool, canceladas_count: int, mensagem_aviso: str).
        """
        if not HAS_RCLPY or not HAS_NAV2_ACTION or not self.nav_action_client:
            return False, 0, "nav2_msgs ou ActionClient de navegação indisponível no backend."

        try:
            if not self.nav_action_client.wait_for_server(timeout_sec=timeout_sec):
                return True, 0, "Servidor /navigate_to_pose indisponível (nenhuma meta do Nav2 no ar)."

            if hasattr(self.nav_action_client, 'cancel_all_goals_async'):
                fut = self.nav_action_client.cancel_all_goals_async()
                t0 = time.time()
                while not fut.done() and (time.time() - t0) < timeout_sec:
                    time.sleep(0.02)
                if fut.done():
                    res = fut.result()
                    goals_cancelled = len(getattr(res, 'goals_canceling', [])) if res else 1
                    return True, goals_cancelled, ""
                return False, 0, "Timeout aguardando confirmação de cancelamento da meta do Nav2."
            return True, 0, ""
        except Exception as e:
            return False, 0, f"Falha ao cancelar meta do Nav2: {e}"

    def send_cmd_vel(self, linear_x: float, angular_z: float, duration_sec: float = 0.5, hz: float = 20.0):
        """Publica comandos de velocidade em rajada parametrizada (default 0.5s a 20 Hz)."""
        if HAS_RCLPY and self.cmd_vel_pub:
            t = Twist()
            t.linear.x = float(linear_x)
            t.angular.z = float(angular_z)

            ts = TwistStamped()
            ts.header.frame_id = "base_link"
            ts.twist = t

            iterations = max(10, int(duration_sec * hz))
            sleep_dt = 1.0 / hz

            def _burst():
                for _ in range(iterations):
                    try:
                        self.cmd_vel_pub.publish(t)
                        if hasattr(self, 'cmd_vel_stamped_pub') and self.cmd_vel_stamped_pub:
                            ts.header.stamp = self.get_clock().now().to_msg()
                            self.cmd_vel_stamped_pub.publish(ts)
                    except Exception:
                        pass
                    time.sleep(sleep_dt)
            threading.Thread(target=_burst, daemon=True).start()

    def publish_initial_pose(self, x: float = 0.0, y: float = 0.0, yaw: float = 0.0) -> tuple:
        if not HAS_RCLPY or not self.initialpose_pub:
            return False, "rclpy não inicializado no nó para publicar /initialpose"

        try:
            msg = PoseWithCovarianceStamped()
            msg.header.frame_id = "map"
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.pose.pose.position.x = float(x)
            msg.pose.pose.position.y = float(y)
            msg.pose.pose.position.z = 0.0

            half_yaw = float(yaw) * 0.5
            msg.pose.pose.orientation.z = math.sin(half_yaw)
            msg.pose.pose.orientation.w = math.cos(half_yaw)

            cov = [0.0] * 36
            cov[0] = 0.25
            cov[7] = 0.25
            cov[35] = 0.06853891945200942
            msg.pose.covariance = cov

            for _ in range(3):
                msg.header.stamp = self.get_clock().now().to_msg()
                self.initialpose_pub.publish(msg)
                time.sleep(0.2)

            return True, f"Pose inicial (x={x}, y={y}, yaw={yaw}) publicada com sucesso em /initialpose!"
        except Exception as e:
            return False, f"Erro ao publicar /initialpose: {e}"

    def telemetry_fresh(self) -> bool:
        return (time.time() - self.last_telemetry_time) < TELEMETRY_TTL

    def get_status(self) -> Dict:
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
