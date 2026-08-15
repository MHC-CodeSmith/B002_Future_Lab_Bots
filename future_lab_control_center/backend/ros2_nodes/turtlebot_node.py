import os
import time
import math
import threading
import subprocess
from typing import Dict, Optional

os.environ["ROS_DOMAIN_ID"] = "0"
os.environ["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
os.environ.pop("ROS_AUTOMATIC_DISCOVERY_RANGE", None)
os.environ["ROS_SUPER_CLIENT"] = "True"
os.environ["ROS_DISCOVERY_SERVER"] = "192.168.0.129:11811;"

JAZZY_ENV_CMD = (
    "source /opt/ros/jazzy/setup.bash && "
    "source /home/future-lab/B002_Future_Lab_Bots/turtlebot4_jazzy/setup.bash && "
    "unset ROS_AUTOMATIC_DISCOVERY_RANGE && "
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
    from sensor_msgs.msg import BatteryState, CompressedImage, Image, LaserScan
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

try:
    from action_msgs.srv import CancelGoal
    from action_msgs.msg import GoalStatus, GoalStatusArray
    HAS_CANCEL_SRV = True
except ImportError:
    HAS_CANCEL_SRV = False
    GoalStatus = None
    GoalStatusArray = None


TELEMETRY_TTL = 5.0   # s sem mensagem da BASE = telemetria inválida
SCAN_TTL = 2.0        # /scan normalmente publica a varios Hz; 2 s prova fluxo parado
FRAME_TTL = 3.0       # s sem frame da OAK-D = câmera sem sinal
FRAME_MIN_INTERVAL = 1.0 / 15.0   # processa no maximo 15 fps
AMCL_TTL = 120.0      # o AMCL so publica quando atualiza; parado, fica em silencio
COV_XY_MAX = 0.05      # m² (em movimento)
COV_YAW_MAX = 0.06     # rad² (em movimento)
COV_XY_MAX_DOCK = 0.09 # m² (~30 cm de sigma; estado docado)
COV_YAW_MAX_DOCK = 0.12 # rad² (~20 graus de sigma; estado docado)

if HAS_RCLPY:
    QOS_LATCHED = QoSProfile(
        depth=1,
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    )
    QOS_INITIAL_POSE = QoSProfile(
        depth=10,
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.VOLATILE,
    )
else:
    QOS_LATCHED = 10
    QOS_INITIAL_POSE = 10


class TurtleBotNode(Node if HAS_RCLPY else object):
    def __init__(self):
        self.battery_percentage: Optional[float] = None
        self.battery_current: Optional[float] = None
        self.is_docked: bool = False
        self.current_pose: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.amcl_pose: Optional[Dict[str, float]] = None
        self.amcl_cov: Optional[Dict[str, float]] = None
        self.amcl_source: Optional[str] = None
        self.amcl_initialized: bool = False
        self.last_amcl_time: float = 0.0
        self.last_telemetry_time: float = 0.0
        self.last_frame_time: float = 0.0
        self.last_scan_time: float = 0.0
        self.last_scan_frame: Optional[str] = None
        self._last_compressed_time: float = 0.0
        self.latest_jpeg_frame: Optional[bytes] = None
        self.init_errors: list = []
        self._nav_status_lock = threading.Lock()
        self._nav_goal_statuses: Dict[bytes, int] = {}
        self.last_nav_status_time: float = 0.0
        self._initial_pose_ack = threading.Event()
        self._initial_pose_request_started: float = 0.0

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
                    # O AMCL do TurtleBot 4 solicita BEST_EFFORT em /initialpose.
                    # Igualar o QoS evita a perda observada entre o container e
                    # o reader do AMCL no host usando Fast DDS Discovery Server.
                    self.initialpose_pub = self.create_publisher(
                        PoseWithCovarianceStamped,
                        "/initialpose",
                        QOS_INITIAL_POSE,
                    )
                except Exception as e:
                    err = f"Falha ao criar publishers: {type(e).__name__}: {e}"
                    print(f"[ERRO TB4] {err}")
                    self.init_errors.append(err)

                if HAS_NAV2_ACTION:
                    try:
                        self.nav_action_client = ActionClient(self, NavigateToPose, "/navigate_to_pose", callback_group=self._cb_cli)
                    except Exception as e:
                        err = f"Falha ao criar ActionClient /navigate_to_pose: {type(e).__name__}: {e}"
                        print(f"[ERRO TB4] {err}")
                        self.init_errors.append(err)

                self.cancel_nav_client = None
                if HAS_RCLPY and HAS_CANCEL_SRV:
                    try:
                        self.cancel_nav_client = self.create_client(
                            CancelGoal,
                            "/navigate_to_pose/_action/cancel_goal",
                            callback_group=self._cb_cli,
                        )
                    except Exception as e:
                        err = f"Falha ao criar cliente /navigate_to_pose/_action/cancel_goal: {type(e).__name__}: {e}"
                        print(f"[ERRO TB4] {err}")
                        self.init_errors.append(err)

                if HAS_CANCEL_SRV:
                    try:
                        self.create_subscription(
                            GoalStatusArray,
                            "/navigate_to_pose/_action/status",
                            self._nav_status_callback,
                            QOS_LATCHED,
                            callback_group=self._cb_cli,
                        )
                    except Exception as e:
                        err = f"Falha ao assinar /navigate_to_pose/_action/status: {type(e).__name__}: {e}"
                        print(f"[ERRO TB4] {err}")
                        self.init_errors.append(err)

                try:
                    self.create_subscription(BatteryState, "/battery_state", self._battery_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                except Exception as e:
                    err = f"Falha ao assinar /battery_state: {type(e).__name__}: {e}"
                    print(f"[ERRO TB4] {err}")
                    self.init_errors.append(err)

                try:
                    self.create_subscription(Odometry, "/odom", self._odom_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                except Exception as e:
                    err = f"Falha ao assinar /odom: {type(e).__name__}: {e}"
                    print(f"[ERRO TB4] {err}")
                    self.init_errors.append(err)

                try:
                    self.create_subscription(
                        LaserScan,
                        "/scan",
                        self._scan_callback,
                        qos_profile_sensor_data,
                        callback_group=self._cb_sub,
                    )
                except Exception as e:
                    err = f"Falha ao assinar /scan: {type(e).__name__}: {e}"
                    print(f"[ERRO TB4] {err}")
                    self.init_errors.append(err)

                try:
                    self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self._amcl_callback, QOS_LATCHED, callback_group=self._cb_sub)
                except Exception as e:
                    err = f"Falha ao assinar /amcl_pose: {type(e).__name__}: {e}"
                    print(f"[ERRO TB4] {err}")
                    self.init_errors.append(err)

                try:
                    self.create_subscription(CompressedImage, "/oakd/rgb/preview/image_raw/compressed", self._compressed_image_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                    self.create_subscription(Image, "/oakd/rgb/preview/image_raw", self._raw_image_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                except Exception as e:
                    err = f"Falha ao assinar tópicos OAK-D: {type(e).__name__}: {e}"
                    print(f"[ERRO TB4] {err}")
                    self.init_errors.append(err)

                if HAS_CREATE_MSGS and hasattr(DockStatus, '_TYPE_SUPPORT'):
                    try:
                        self.create_subscription(DockStatus, "/dock_status", self._dock_status_callback, qos_profile_sensor_data, callback_group=self._cb_sub)
                    except Exception as e:
                        err = f"Falha ao assinar /dock_status: {type(e).__name__}: {e}"
                        print(f"[ERRO TB4] {err}")
                        self.init_errors.append(err)

                try:
                    self.start_delivery_cli = self.create_client(Trigger, "/start_delivery", callback_group=self._cb_cli)
                    self.start_failure_cli = self.create_client(Trigger, "/start_failure", callback_group=self._cb_cli)
                    self.start_restock_cli = self.create_client(Trigger, "/start_restock", callback_group=self._cb_cli)
                    self.stop_mission_cli = self.create_client(Trigger, "/stop_mission", callback_group=self._cb_cli)
                except Exception as e:
                    err = f"Falha ao criar clientes de missão: {type(e).__name__}: {e}"
                    print(f"[ERRO TB4] {err}")
                    self.init_errors.append(err)

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
            agora = time.time()
            if (agora - self.last_frame_time) < FRAME_MIN_INTERVAL:
                return
            self._last_compressed_time = agora
            self.latest_jpeg_frame = bytes(msg.data)
            self.last_frame_time = agora
        except Exception:
            pass

    def _raw_image_callback(self, msg):
        try:
            agora = time.time()
            if (agora - self.last_frame_time) < FRAME_MIN_INTERVAL:
                return
            if (agora - self._last_compressed_time) < 2.0:
                return
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
                    self.last_frame_time = agora
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

    def _scan_callback(self, msg):
        try:
            self.last_scan_time = time.time()
            self.last_scan_frame = str(msg.header.frame_id or "")
        except Exception as e:
            print(f"[WARN TB4] Scan callback error: {e}")

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
            self.amcl_source = "amcl_pose_topic"
            self.amcl_initialized = True
            if self._initial_pose_request_started and self.last_amcl_time >= self._initial_pose_request_started:
                self._initial_pose_ack.set()
        except Exception as e:
            print(f"[WARN TB4] AMCL callback error: {e}")

    def get_amcl(self) -> Dict:
        if self.amcl_pose is None or not self.amcl_initialized:
            return {"amcl_ok": False, "converged": False, "converged_dock": False,
                    "pose": None, "covariance": None, "age_s": None,
                    "initialized": False, "source": self.amcl_source,
                    "motivo": "nenhuma mensagem recebida em /amcl_pose",
                    "init_errors": self.init_errors}
        idade = round(time.time() - self.last_amcl_time, 1)
        fresh = bool(idade < AMCL_TTL)
        c = self.amcl_cov
        converged = bool(c is not None and fresh and (
            c["x"] < COV_XY_MAX and c["y"] < COV_XY_MAX and c["yaw"] < COV_YAW_MAX
        ))
        converged_dock = bool(c is not None and fresh and (
            c["x"] < COV_XY_MAX_DOCK and c["y"] < COV_XY_MAX_DOCK
            and c["yaw"] < COV_YAW_MAX_DOCK
        ))
        motivo = "" if fresh else f"ultima leitura ha {idade}s"
        if fresh and c is None:
            motivo = "pose medida, mas covariancia nao foi recebida"
        return {"amcl_ok": fresh, "converged": converged, "converged_dock": converged_dock,
                "pose": self.amcl_pose, "covariance": c, "age_s": idade,
                "initialized": True, "source": self.amcl_source, "motivo": motivo,
                "init_errors": self.init_errors}

    def record_external_amcl_measurement(self, pose: Dict, covariance: Optional[Dict], source: str) -> bool:
        """Registra somente valores finitos medidos pelo helper ROS do host."""
        try:
            measured_pose = {key: float(pose[key]) for key in ("x", "y", "yaw")}
            if not all(math.isfinite(value) for value in measured_pose.values()):
                return False
            measured_cov = None
            if covariance is not None:
                measured_cov = {
                    key: float(covariance[key]) for key in ("x", "y", "yaw")
                }
                if not all(math.isfinite(value) for value in measured_cov.values()):
                    return False
            self.amcl_pose = {key: round(value, 4) for key, value in measured_pose.items()}
            self.amcl_cov = (
                {key: round(value, 5) for key, value in measured_cov.items()}
                if measured_cov is not None else None
            )
            self.last_amcl_time = time.time()
            self.amcl_source = source
            self.amcl_initialized = True
            return True
        except (KeyError, TypeError, ValueError):
            return False

    def clear_amcl_measurement(self):
        self.amcl_pose = None
        self.amcl_cov = None
        self.amcl_source = None
        self.amcl_initialized = False
        self.last_amcl_time = 0.0

    def get_scan_status(self) -> Dict:
        publisher_count = self.count_publishers("/scan") if HAS_RCLPY else 0
        age = None if self.last_scan_time == 0.0 else round(time.time() - self.last_scan_time, 2)
        fresh = bool(age is not None and age < SCAN_TTL)
        if fresh:
            reason = ""
        elif publisher_count == 0:
            reason = "nenhum publisher de /scan"
        elif self.last_scan_time == 0.0:
            reason = "publisher existe, mas nenhuma mensagem /scan foi recebida"
        else:
            reason = f"ultima mensagem /scan ha {age}s"
        return {
            "fresh": fresh,
            "age_s": age,
            "frame_id": self.last_scan_frame,
            "publisher_count": publisher_count,
            "reason": reason,
        }

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

    def _nav_status_callback(self, msg):
        """Mantem o snapshot autoritativo publicado pelo action server do Nav2."""
        try:
            statuses = {
                bytes(item.goal_info.goal_id.uuid): int(item.status)
                for item in msg.status_list
            }
            with self._nav_status_lock:
                self._nav_goal_statuses = statuses
                self.last_nav_status_time = time.time()
        except Exception as e:
            print(f"[WARN TB4] Falha ao processar status de /navigate_to_pose: {e}")

    def _nav_goals_still_active(self, goal_ids) -> list[bytes]:
        active_states = {
            GoalStatus.STATUS_ACCEPTED,
            GoalStatus.STATUS_EXECUTING,
            GoalStatus.STATUS_CANCELING,
        }
        with self._nav_status_lock:
            statuses = dict(self._nav_goal_statuses)
        return [goal_id for goal_id in goal_ids if statuses.get(goal_id) in active_states]

    def cancel_all_nav_goals(self, timeout_sec: float = 3.0, confirm_sec: float = 5.0) -> tuple:
        """Cancela todas as metas ativas de /navigate_to_pose.

        Usa o serviço <action>/_action/cancel_goal (action_msgs/srv/CancelGoal).
        Requisicao com goal_id zerado e stamp zerado = cancelar TODAS as metas.

        Retorna (cancelado, quantas, aviso).
        cancelado=True SOMENTE quando o servidor aceita a solicitacao e as metas
        deixam os estados ACCEPTED/EXECUTING/CANCELING.
        """
        if not HAS_RCLPY or not HAS_CANCEL_SRV or self.cancel_nav_client is None:
            return False, 0, ("Cliente de cancelamento indisponível no backend — "
                              "o botão de parada NÃO cancela metas.")

        if not self.cancel_nav_client.wait_for_service(timeout_sec=timeout_sec):
            return False, 0, ("Serviço /navigate_to_pose/_action/cancel_goal INALCANÇÁVEL — "
                              "nenhuma meta foi cancelada. Se o robô estiver em movimento, "
                              "use o botão físico da Create 3.")

        try:
            req = CancelGoal.Request()  # goal_id e stamp zerados = todas as metas
            request_started_at = time.time()
            fut = self.cancel_nav_client.call_async(req)
            t0 = time.time()
            while not fut.done() and (time.time() - t0) < timeout_sec:
                time.sleep(0.02)
            if not fut.done():
                return False, 0, ("Timeout aguardando resposta do cancelamento — não é "
                                  "possível garantir que a meta foi cancelada.")

            res = fut.result()
            if res is None:
                return False, 0, "Resposta vazia do serviço de cancelamento."

            goals_canceling = list(getattr(res, "goals_canceling", []) or [])
            quantas = len(goals_canceling)
            code = int(getattr(res, "return_code", 0))

            # action_msgs/srv/CancelGoal: somente ERROR_NONE confirma aceite.
            # ERROR_REJECTED/UNKNOWN_GOAL_ID/GOAL_TERMINATED nao sao sucesso.
            if code != CancelGoal.Response.ERROR_NONE:
                return False, 0, (
                    f"Servidor de action rejeitou o cancelamento (return_code={code}); "
                    "nenhuma parada foi confirmada."
                )

            if not goals_canceling:
                return True, 0, "Servidor confirmou que não havia meta ativa para cancelar."

            goal_ids = {bytes(item.goal_id.uuid) for item in goals_canceling}
            deadline = time.monotonic() + confirm_sec
            while time.monotonic() < deadline:
                with self._nav_status_lock:
                    status_observed_after_request = self.last_nav_status_time >= request_started_at
                if status_observed_after_request and not self._nav_goals_still_active(goal_ids):
                    return True, quantas, ""
                time.sleep(0.05)

            still_active = self._nav_goals_still_active(goal_ids)
            with self._nav_status_lock:
                status_observed_after_request = self.last_nav_status_time >= request_started_at
            if not status_observed_after_request:
                return False, quantas, (
                    f"Cancelamento aceito para {quantas} meta(s), mas o topico de status "
                    f"nao confirmou a transicao em {confirm_sec:.1f}s."
                )
            return False, quantas, (
                f"Cancelamento aceito para {quantas} meta(s), mas {len(still_active)} "
                f"continuaram ativas apos {confirm_sec:.1f}s."
            )

        except Exception as e:
            return False, 0, f"Falha ao cancelar meta do Nav2: {type(e).__name__}: {e}"

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
            return True
        return False

    def publish_initial_pose(self, x: float, y: float, yaw: float, confirm_sec: float = 5.0) -> tuple:
        if not HAS_RCLPY or not self.initialpose_pub:
            return False, "rclpy não inicializado no nó para publicar /initialpose", None

        subscribers = self.count_subscribers("/initialpose")
        if subscribers < 1:
            return False, (
                "AMCL não está inscrito em /initialpose; inicie e ative a localização antes "
                "de definir a pose."
            ), None

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

            self._initial_pose_ack.clear()
            self._initial_pose_request_started = time.time()
            for _ in range(5):
                msg.header.stamp = self.get_clock().now().to_msg()
                self.initialpose_pub.publish(msg)
                time.sleep(0.2)

            confirmed = self._initial_pose_ack.wait(timeout=confirm_sec)
            self._initial_pose_request_started = 0.0
            if not confirmed:
                return False, (
                    f"Pose publicada para {subscribers} subscriber(s), mas nenhuma nova "
                    f"/amcl_pose confirmou o recebimento em {confirm_sec:.1f}s."
                ), None

            observed = dict(self.amcl_pose) if self.amcl_pose else None
            print(f"[INFO TB4] Pose inicial confirmada pelo AMCL: solicitada=({x}, {y}, {yaw}), observada={observed}")
            return True, (
                f"Pose inicial confirmada pelo AMCL: x={observed.get('x') if observed else x}, "
                f"y={observed.get('y') if observed else y}, "
                f"yaw={observed.get('yaw') if observed else yaw}."
            ), observed
        except Exception as e:
            self._initial_pose_request_started = 0.0
            return False, f"Erro ao publicar /initialpose: {e}", None

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
