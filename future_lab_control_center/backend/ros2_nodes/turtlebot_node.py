# ============================================================
# turtlebot_node.py — Nó ROS 2 de Ponte com o TurtleBot 4 (Skeleton)
# ============================================================
import time
from typing import Dict, Optional
import rclpy
from rclpy.node import Node

class TurtleBotNode(Node):
    def __init__(self):
        super().__init__("future_lab_turtlebot_node")
        self.battery_percentage: float = 100.0
        self.is_docked: bool = True
        self.current_pose: Dict[str, float] = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.get_logger().info("Nó do TurtleBot 4 inicializado (Aguardando robô na rede)...")

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
        if not rclpy.ok():
            rclpy.init()
        _tb_node = TurtleBotNode()
    return _tb_node
