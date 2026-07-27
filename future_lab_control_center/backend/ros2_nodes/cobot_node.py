# ============================================================
# cobot_node.py — Nó ROS 2 de Ponte com o Manipulador MyCobot 280
# ============================================================
import os
import sys
import time
import yaml
import threading
from datetime import datetime
from typing import Dict, List, Optional

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from std_srvs.srv import Trigger
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import PlanningOptions, Constraints, JointConstraint, MotionPlanRequest

JOINT_NAMES = [
    "joint2_to_joint1", "joint3_to_joint2", "joint4_to_joint3",
    "joint5_to_joint4", "joint6_to_joint5", "joint6output_to_joint6",
]
GROUP = "mycobot_arm"
POSES_FILE = "/home/future-lab/B002_Future_Lab_Bots/cobot/mycobot_docker/custom_ws/config/test_table_poses.yaml"
REQUIRED_POSES = ["home", "scan", "pick_approach", "pick", "place_approach", "place"]

class CobotNode(Node):
    def __init__(self):
        super().__init__("future_lab_cobot_node")
        
        self.move_cli = ActionClient(self, MoveGroup, "/move_action")
        self.pump_on_cli = self.create_client(Trigger, "/pump_on")
        self.pump_off_cli = self.create_client(Trigger, "/pump_off")
        self.release_cli = self.create_client(Trigger, "/release_servos")
        self.lock_cli = self.create_client(Trigger, "/lock_servos")
        
        self.current_joints: Optional[List[float]] = None
        self.last_yolo_msg: Optional[Dict] = None
        self.pump_active: bool = False
        
        qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST, depth=10)
        self.create_subscription(JointState, "/joint_states", self._js_cb, 10)
        self.create_subscription(JointState, "/joint_states_raw", self._js_cb, 10)
        self.create_subscription(String, "/product_class", self._yolo_cb, qos)
        
        self.poses: Dict[str, List[float]] = {}
        self.load_poses()

    def load_poses(self):
        if os.path.exists(POSES_FILE):
            try:
                with open(POSES_FILE, "r") as f:
                    self.poses = yaml.safe_load(f) or {}
            except Exception as e:
                self.get_logger().error(f"Erro ao carregar {POSES_FILE}: {e}")
                self.poses = {}
        else:
            self.poses = {}

    def save_poses(self) -> bool:
        os.makedirs(os.path.dirname(POSES_FILE), exist_ok=True)
        self.poses["_last_saved"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(POSES_FILE, "w") as f:
                yaml.safe_dump(self.poses, f, default_flow_style=None, sort_keys=True)
            return True
        except Exception as e:
            self.get_logger().error(f"Erro ao salvar poses: {e}")
            return False

    def clear_poses(self) -> bool:
        self.poses = {}
        if os.path.exists(POSES_FILE):
            try:
                os.remove(POSES_FILE)
                return True
            except Exception as e:
                self.get_logger().error(f"Erro ao remover {POSES_FILE}: {e}")
                return False
        return True

    def _js_cb(self, msg: JointState):
        if set(JOINT_NAMES).issubset(set(msg.name)):
            idx = {n: i for i, n in enumerate(msg.name)}
            self.current_joints = [float(msg.position[idx[n]]) for n in JOINT_NAMES]

    def _yolo_cb(self, msg: String):
        data = (msg.data or "").strip()
        if not data:
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

    def call_trigger_service(self, cli: ActionClient, label: str, timeout_sec: float = 3.0) -> bool:
        if not cli.service_is_ready():
            self.get_logger().warn(f"Serviço de {label} indisponível.")
            return False
        req = Trigger.Request()
        fut = cli.call_async(req)
        t0 = time.time()
        while not fut.done() and (time.time() - t0) < timeout_sec:
            time.sleep(0.05)
        if not fut.done():
            return False
        res = fut.result()
        return bool(res and res.success)

    def set_pump(self, on: bool) -> bool:
        cli = self.pump_on_cli if on else self.pump_off_cli
        ok = self.call_trigger_service(cli, "Bomba ON" if on else "Bomba OFF")
        if ok:
            self.pump_active = on
        return ok

    def goto_pose(self, pose_name: str, velocity_scaling: float = 0.20) -> bool:
        if pose_name not in self.poses:
            self.get_logger().error(f"Pose '{pose_name}' não gravada.")
            return False

        target_joints = self.poses[pose_name]
        if not self.move_cli.wait_for_server(timeout_sec=3.0):
            self.get_logger().error("Action Server /move_action indisponível.")
            return False

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
        while not send_fut.done() and (time.time() - t0) < 5.0:
            time.sleep(0.05)
        if not send_fut.done():
            return False

        gh = send_fut.result()
        if gh is None or not gh.accepted:
            return False

        res_fut = gh.get_result_async()
        t0 = time.time()
        while not res_fut.done() and (time.time() - t0) < 15.0:
            time.sleep(0.05)
        if not res_fut.done():
            return False

        res = res_fut.result()
        return bool(res and res.result.error_code.val == 1)

# Instância Singleton gerenciada no backend
_cobot_node: Optional[CobotNode] = None
_executor: Optional[MultiThreadedExecutor] = None

def get_cobot_node() -> CobotNode:
    global _cobot_node, _executor
    if _cobot_node is None:
        if not rclpy.ok():
            rclpy.init()
        _cobot_node = CobotNode()
        _executor = MultiThreadedExecutor()
        _executor.add_node(_cobot_node)
        spin_thread = threading.Thread(target=_executor.spin, daemon=True)
        spin_thread.start()
    return _cobot_node
