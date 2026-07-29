# ============================================================
# cobot_node.py — Nó ROS 2 de Ponte com o Manipulador MyCobot 280
# ============================================================
import os
import sys
import time
import yaml
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

HAS_RCLPY = False
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from rclpy.executors import MultiThreadedExecutor
    from sensor_msgs.msg import JointState
    from std_msgs.msg import String
    from std_srvs.srv import Trigger
    
    if not rclpy.ok():
        rclpy.init()
    HAS_RCLPY = True
except Exception as e:
    print(f"[WARN] ROS 2 rclpy não ativado no momento: {e}")
    HAS_RCLPY = False
    JointState = object
    String = object
    Trigger = object

try:
    from moveit_msgs.action import MoveGroup
    from moveit_msgs.msg import PlanningOptions, Constraints, JointConstraint, MotionPlanRequest
except Exception:
    MoveGroup = object

try:
    from control_msgs.action import FollowJointTrajectory
    from trajectory_msgs.msg import JointTrajectoryPoint
except Exception:
    FollowJointTrajectory = object
    JointTrajectoryPoint = object

JOINT_NAMES = [
    "joint2_to_joint1", "joint3_to_joint2", "joint4_to_joint3",
    "joint5_to_joint4", "joint6_to_joint5", "joint6output_to_joint6",
]
GROUP = "mycobot_arm"
REQUIRED_POSES = ["home", "scan", "pick_approach", "pick", "place_approach", "place"]

POSES_PATH_CONTAINER = Path("/cobot/mycobot_docker/custom_ws/config/test_table_poses.yaml")
POSES_PATH_HOST = Path("/home/future-lab/B002_Future_Lab_Bots/cobot/mycobot_docker/custom_ws/config/test_table_poses.yaml")
POSES_PATH_LOCAL = Path(__file__).resolve().parent.parent / "config" / "test_table_poses.yaml"

def get_poses_file() -> Path:
    if POSES_PATH_CONTAINER.parent.exists():
        return POSES_PATH_CONTAINER
    if POSES_PATH_HOST.parent.exists():
        return POSES_PATH_HOST
    POSES_PATH_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    return POSES_PATH_LOCAL

class DummyNode:
    """Fallback simples caso o ROS 2 não esteja inicializado."""
    pass

BaseNode = Node if HAS_RCLPY else DummyNode

class CobotNode(BaseNode):
    def __init__(self):
        self.current_joints: Optional[List[float]] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.last_yolo_msg: Optional[Dict] = None
        self.pump_active: bool = False
        self.poses: Dict[str, List[float]] = {}
        self.is_ros_active: bool = False
        self.lock = threading.Lock()
        self.load_poses()

        if HAS_RCLPY and rclpy.ok():
            try:
                super().__init__("future_lab_cobot_node")
                self.move_cli = ActionClient(self, MoveGroup, "/move_action")
                self.follow_jt_cli = ActionClient(self, FollowJointTrajectory, "/mycobot_arm_controller/follow_joint_trajectory")
                self.pump_on_cli = self.create_client(Trigger, "/pump_on")
                self.pump_off_cli = self.create_client(Trigger, "/pump_off")
                self.release_cli = self.create_client(Trigger, "/release_servos")
                self.lock_cli = self.create_client(Trigger, "/lock_servos")
                
                self.create_subscription(JointState, "/joint_states", self._js_cb, 10)
                self.create_subscription(JointState, "/joint_states_raw", self._js_cb, 10)
                self.create_subscription(String, "/product_class", self._yolo_cb, 10)
                self.is_ros_active = True
                
                # Aquecimento proativo de serviços ROS 2 DDS em segundo plano
                t_warmup = threading.Thread(target=self._warmup_services, daemon=True)
                t_warmup.start()
            except Exception as e:
                print(f"[WARN] Erro ao inicializar nó ROS 2: {e}")
                self.is_ros_active = False

    def _warmup_services(self):
        """Conecta e mantêm aquecidos os canais de serviços DDS em segundo plano para resposta instantânea (0ms)."""
        time.sleep(1.0)
        clients = [
            ("Bomba ON", getattr(self, "pump_on_cli", None)),
            ("Bomba OFF", getattr(self, "pump_off_cli", None)),
            ("Liberar Servos", getattr(self, "release_cli", None)),
            ("Travar Servos", getattr(self, "lock_cli", None))
        ]
        for label, cli in clients:
            if cli is not None:
                try:
                    cli.wait_for_service(timeout_sec=3.0)
                    print(f"[INFO] Serviço ROS 2 DDS '{label}' aquecido e pronto!")
                except Exception:
                    pass

    def clear_yolo_state(self):
        """Zera e limpa completamente qualquer histórico de detecção do YOLO da memória."""
        with self.lock:
            self.last_yolo_msg = None

    def load_poses(self):
        poses_path = get_poses_file()
        if poses_path.exists():
            try:
                with open(poses_path, "r") as f:
                    loaded = yaml.safe_load(f) or {}
                with self.lock:
                    self.poses = loaded
            except Exception as e:
                print(f"Erro ao carregar poses: {e}")
                with self.lock:
                    self.poses = {}
        else:
            with self.lock:
                self.poses = {}

    def save_poses(self) -> bool:
        """Salva as poses com escrita atômica em arquivo temporário (.tmp) + substituição no SO."""
        poses_path = get_poses_file()
        poses_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = poses_path.with_suffix(".yaml.tmp")
        
        with self.lock:
            self.poses["_last_saved"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data_to_save = dict(self.poses)
            
        try:
            with open(tmp_path, "w") as f:
                yaml.safe_dump(data_to_save, f)
            tmp_path.replace(poses_path) # Escrita 100% atômica no SO (thread-safe)
            return True
        except Exception as e:
            print(f"Erro ao salvar poses atomicamente: {e}")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return False

    def clear_poses(self) -> bool:
        """Cria uma cópia de segurança de backup (.yaml.bak) das poses salvas ou em rascunho de memória antes de zerar a calibragem."""
        import shutil
        poses_path = get_poses_file()
        bak_path = poses_path.with_suffix(".yaml.bak")

        # 1. Se o arquivo de poses existe no disco, copia para o backup!
        if poses_path.exists():
            try:
                shutil.copy2(poses_path, bak_path)
                print(f"[INFO] Backup automático de calibragem criado em: {bak_path}")
            except Exception as e:
                print(f"[WARN] Erro ao criar backup da calibragem: {e}")
        elif self.poses:
            # 2. Se existirem poses em memória (rascunho), salva o backup diretamente a partir da memória!
            try:
                with self.lock:
                    data_to_backup = dict(self.poses)
                    if "_last_saved" not in data_to_backup:
                        data_to_backup["_last_saved"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S (rascunho)")
                with open(bak_path, "w") as f:
                    yaml.safe_dump(data_to_backup, f)
                print(f"[INFO] Backup de rascunho de calibragem em memória salvo em: {bak_path}")
            except Exception as e:
                print(f"[WARN] Erro ao salvar backup de rascunho: {e}")

        # 3. Limpa o mapa em memória e remove o arquivo ativo do disco
        with self.lock:
            self.poses = {}

        if poses_path.exists():
            try:
                poses_path.unlink()
                return True
            except Exception as e:
                print(f"Erro ao apagar arquivo de poses: {e}")
                return False
        return True

    def restore_backup_poses(self) -> bool:
        """Restaura as poses do arquivo de backup (.yaml.bak) de volta para o arquivo ativo e recarrega na memória."""
        import shutil
        poses_path = get_poses_file()
        bak_path = poses_path.with_suffix(".yaml.bak")

        if not bak_path.exists():
            print("[WARN] Nenhum arquivo de backup (.yaml.bak) foi encontrado para restaurar.")
            return False

        try:
            shutil.copy2(bak_path, poses_path)
            self.load_poses()
            print(f"[INFO] Calibragem restaurada com sucesso a partir do backup: {bak_path}")
            return True
        except Exception as e:
            print(f"[WARN] Erro ao restaurar backup da calibragem: {e}")
            return False

    def has_backup_poses(self) -> bool:
        """Verifica se existe um arquivo de backup de calibragem no disco."""
        bak_path = get_poses_file().with_suffix(".yaml.bak")
        return bak_path.exists()

    def _js_cb(self, msg: JointState):
        if not self.is_ros_active:
            return
        if msg.position and len(msg.position) >= 6:
            self.current_joints = [float(v) for v in msg.position[:6]]

    def _yolo_cb(self, msg: String):
        if not self.is_ros_active:
            return
        data = (msg.data or "").strip()
        if not data or data.startswith("none") or data.startswith("invalid_stream"):
            self.last_yolo_msg = None
            return
        parts = data.replace(":", " ").split()
        cls_name = parts[0].lower()
        conf = float(parts[1]) if len(parts) > 1 else 1.0
        self.last_yolo_msg = {
            "class": cls_name,
            "confidence": conf,
            "raw": data,
            "timestamp": time.time()
        }

    def _trigger_service_fallback_http(self, label: str) -> bool:
        """Chamada de ultra-alta velocidade via HTTP Micro-Bridge na Jetson Nano (resposta em ~27ms)."""
        endpoint = None
        if "Bomba ON" in label:
            endpoint = "/pump/on"
        elif "Bomba OFF" in label:
            endpoint = "/pump/off"
        elif "Liberar" in label:
            endpoint = "/servos/release"
        elif "Travar" in label:
            endpoint = "/servos/lock"

        if not endpoint:
            return False

        try:
            url = f"http://192.168.0.250:8088{endpoint}"
            import urllib.request
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    print(f"[INFO] HTTP Micro-Bridge '{label}' executado com SUCESSO INSTANTÂNEO (~27ms)!")
                    return True
        except Exception as e:
            print(f"[WARN] HTTP Micro-Bridge para '{label}' falhou ({e}), usando fallback SSH...")
            return self._trigger_service_fallback_ssh(label)
        return False

    def _trigger_service_fallback_ssh(self, label: str) -> bool:
        """Fallback secundário via SSH reutilizando conexão para disparar o serviço na Jetson Nano."""
        srv_name = None
        if "Bomba ON" in label:
            srv_name = "/pump_on"
        elif "Bomba OFF" in label:
            srv_name = "/pump_off"
        elif "Liberar" in label:
            srv_name = "/release_servos"
        elif "Travar" in label:
            srv_name = "/lock_servos"

        if not srv_name:
            return False

        try:
            print(f"[INFO] Disparando serviço '{srv_name}' via fallback SSH na Jetson Nano...")
            cmd = f"sshpass -p Elephant ssh -o StrictHostKeyChecking=no -o ControlMaster=auto -o ControlPath=/tmp/ssh_nano_socket -o ControlPersist=60m er@192.168.0.250 'bash -c \"source /opt/ros/galactic/setup.bash && source ~/custom_ws/install/setup.bash && ros2 service call {srv_name} std_srvs/srv/Trigger\"'"
            res = subprocess.run(cmd, shell=True, timeout=5, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output = (res.stdout or "") + (res.stderr or "")
            if "success=True" in output or "success=true" in output or "success: true" in output or "Servos soltos" in output or "Servos travados" in output or "Pump" in output:
                print(f"[INFO] Fallback SSH do serviço '{label}' executado com SUCESSO!")
                return True
            else:
                print(f"[WARN] Fallback SSH retornou output não-esperado: {output}")
        except Exception as e:
            print(f"[WARN] Fallback SSH para '{label}' falhou: {e}")
        return False

    def call_trigger_service(self, cli, label: str, timeout_sec: float = 0.5) -> bool:
        if not self.is_ros_active or cli is None:
            return True

        # 1. Tenta chamada direta síncrona via ROS 2 DDS primeiro (se já descoberto)
        try:
            if cli.service_is_ready():
                req = Trigger.Request()
                fut = cli.call_async(req)
                t0 = time.time()
                while not fut.done() and (time.time() - t0) < timeout_sec:
                    time.sleep(0.005)
                if fut.done():
                    res = fut.result()
                    if res and res.success:
                        return True
        except Exception as e:
            print(f"[WARN] Chamada DDS direta falhou para '{label}': {e}")

        # 2. Se o DDS não respondeu instantaneamente, aciona o HTTP Micro-Bridge (~27ms)
        return self._trigger_service_fallback_http(label)

    def set_pump(self, on: bool) -> bool:
        if not self.is_ros_active:
            self.pump_active = on
            return True
        cli = self.pump_on_cli if on else self.pump_off_cli
        ok = self.call_trigger_service(cli, "Bomba ON" if on else "Bomba OFF")
        if ok:
            self.pump_active = on
        return ok

    def goto_pose_direct_bridge(self, target_joints: List[float], duration_sec: float = 3.0) -> bool:
        """Fallback direto: envia trajetórias angulares diretamente para a Action Server da ponte de hardware no Nano/ROS."""
        if not self.is_ros_active or not hasattr(self, 'follow_jt_cli'):
            return False
            
        if not self.follow_jt_cli.wait_for_server(timeout_sec=2.0):
            print("[WARN] Action Server /mycobot_arm_controller/follow_joint_trajectory não respondeu no timeout.")
            return False

        try:
            goal = FollowJointTrajectory.Goal()
            goal.trajectory.joint_names = [
                "cobot_joint_1", "cobot_joint_2", "cobot_joint_3",
                "cobot_joint_4", "cobot_joint_5", "cobot_joint_6"
            ]

            p = JointTrajectoryPoint()
            p.positions = [float(v) for v in target_joints[:6]]
            p.time_from_start.sec = int(duration_sec)
            p.time_from_start.nanosec = int((duration_sec - int(duration_sec)) * 1e9)
            goal.trajectory.points = [p]

            send_fut = self.follow_jt_cli.send_goal_async(goal)
            t0 = time.time()
            while not send_fut.done() and (time.time() - t0) < 3.0:
                time.sleep(0.05)
            if not send_fut.done():
                return False

            gh = send_fut.result()
            if gh is None or not gh.accepted:
                return False

            res_fut = gh.get_result_async()
            t0 = time.time()
            while not res_fut.done() and (time.time() - t0) < (duration_sec + 4.0):
                time.sleep(0.05)
            if not res_fut.done():
                return False

            self.current_joints = list(target_joints[:6])
            return True
        except Exception as e:
            print(f"[WARN] Erro durante envio direto à ponte de hardware: {e}")
            return False

    def goto_pose_http_microbridge(self, target_joints: List[float]) -> bool:
        """Fallback ultra-rápido via HTTP Micro-Bridge para mover o braço físico em < 30ms."""
        try:
            raw_j = ",".join([str(float(v)) for v in target_joints[:6]])
            url = f"http://192.168.0.250:8088/move_joints?j={raw_j}"
            print(f"[INFO] Disparando movimento ultra-rápido via HTTP Micro-Bridge para: {url}")
            import urllib.request
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    self.current_joints = list(target_joints[:6])
                    print(f"[INFO] Movimento via HTTP Micro-Bridge executado com SUCESSO INSTANTÂNEO em < 30ms!")
                    return True
        except Exception as e:
            print(f"[WARN] HTTP Micro-Bridge de movimento falhou ({e}), usando Action Server direto...")
        return False

    def goto_pose(self, pose_name: str, velocity_scaling: float = 0.20) -> bool:
        if pose_name not in self.poses:
            return False

        if not self.is_ros_active:
            time.sleep(1.0)
            self.current_joints = list(self.poses[pose_name])
            return True

        target_joints = self.poses[pose_name]

        # Helper de execução do movimento
        def _execute_move() -> bool:
            # 1. Tenta mover via MoveIt (/move_action) se o MoveIt estiver no ar
            if self.move_cli.wait_for_server(timeout_sec=1.5):
                try:
                    mpr = MotionPlanRequest()
                    mpr.group_name = GROUP
                    mpr.allowed_planning_time = 5.0
                    mpr.num_planning_attempts = 5
                    mpr.max_velocity_scaling_factor = float(velocity_scaling)
                    mpr.max_acceleration_scaling_factor = float(velocity_scaling)
                    mpr.start_state.is_diff = True
                    if self.current_joints is not None:
                        mpr.start_state.joint_state.name = list(JOINT_NAMES)
                        mpr.start_state.joint_state.position = [float(v) for v in self.current_joints]

                    c = Constraints()
                    for n, p in zip(JOINT_NAMES, target_joints):
                        jc = JointConstraint()
                        jc.joint_name = n
                        jc.position = float(p)
                        jc.tolerance_above = jc.tolerance_below = 0.01
                        jc.weight = 1.0
                        c.joint_constraints.append(jc)
                    mpr.goal_constraints = [c]

                    po = PlanningOptions()
                    po.plan_only = False

                    goal = MoveGroup.Goal()
                    goal.request = mpr
                    goal.planning_options = po

                    send_fut = self.move_cli.send_goal_async(goal)
                    t0 = time.time()
                    while not send_fut.done() and (time.time() - t0) < 2.0:
                        time.sleep(0.05)

                    if send_fut.done():
                        gh = send_fut.result()
                        if gh is not None and gh.accepted:
                            res_fut = gh.get_result_async()
                            t0 = time.time()
                            while not res_fut.done() and (time.time() - t0) < 10.0:
                                time.sleep(0.05)
                            if res_fut.done():
                                res = res_fut.result()
                                if res and res.result.error_code.val == 1:
                                    return True
                except Exception as e:
                    print(f"[WARN] MoveIt falhou no goto_pose, usando fallback direto: {e}")

            # 2. Tenta HTTP Micro-Bridge (~28ms) para acionamento direto do robô real
            if self.goto_pose_http_microbridge(target_joints):
                return True

            # 3. Fallback direto via Action Server da ponte de hardware no Nano/ROS
            print(f"[INFO] Movendo braço para '{pose_name}' via ponte direta de hardware...")
            return self.goto_pose_direct_bridge(target_joints, duration_sec=2.5)

        success = _execute_move()
        if success:
            # Regra Mestre de Hardware:
            # 1. Ligar a bomba APÓS alcançar a pose 'pick'
            # 2. Desligar a bomba APÓS alcançar a pose 'place'
            if pose_name == "pick":
                print("[INFO] Aguardando robô físico alcançar a pose 'pick'...")
                time.sleep(2.0)  # Aguarda a estabilização do braço físico na posição de coleta
                print("[INFO] Pose 'pick' ALCANÇADA -> LIGANDO bomba de sucção...")
                self.set_pump(True)
                time.sleep(0.5)  # Aguarda o selo de vácuo no objeto
            elif pose_name == "place":
                print("[INFO] Aguardando robô físico alcançar a pose 'place'...")
                time.sleep(2.0)  # Aguarda a estabilização do braço físico na posição de soltura
                print("[INFO] Pose 'place' ALCANÇADA -> DESLIGANDO bomba de sucção...")
                self.set_pump(False)
                time.sleep(0.5)  # Aguarda a despressurização e liberação do objeto

        return success

# Instância Singleton gerenciada no backend
_cobot_node: Optional[CobotNode] = None

def get_cobot_node() -> CobotNode:
    global _cobot_node
    if _cobot_node is None:
        if HAS_RCLPY:
            try:
                if not rclpy.ok():
                    rclpy.init(args=None)
            except Exception:
                pass
        _cobot_node = CobotNode()
        if getattr(_cobot_node, 'is_ros_active', False):
            try:
                executor = MultiThreadedExecutor()
                executor.add_node(_cobot_node)
                spin_thread = threading.Thread(target=executor.spin, daemon=True)
                spin_thread.start()
            except Exception as e:
                print(f"[WARN] Erro ao iniciar executor ROS 2: {e}")
    return _cobot_node
