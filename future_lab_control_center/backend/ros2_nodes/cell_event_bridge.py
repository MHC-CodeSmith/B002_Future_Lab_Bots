# ============================================================
# cell_event_bridge.py — Ponte Inter-Robôs (MyCobot 280 + TurtleBot 4)
# ============================================================
"""
Nó orquestrador desacoplado que gerencia a comunicação e sincronização
de tarefas (handshake / cooldown) entre a célula MyCobot 280 e o TurtleBot 4.

Recursos:
  1. Handshake de Prontidão no Ponto de Coleta:
     Informa se o TurtleBot 4 está acoplado ou presente no Ponto de Coleta
     antes de permitir o ciclo de Pick & Place da Célula.
  2. Disparo Automático de Missões baseado na visão YOLO:
     Ao receber a classificação da peça ("blue", "red" ou "failure"),
     despacha a rota correspondente para o TurtleBot 4 via ROS 2 / HTTP.
"""
import time
import threading
from typing import Optional, Dict

_tb4_busy: bool = False
_last_detection_class: Optional[str] = None
_lock = threading.Lock()

def set_turtlebot_busy(busy: bool):
    global _tb4_busy
    with _lock:
        _tb4_busy = busy

def is_turtlebot_busy() -> bool:
    with _lock:
        return _tb4_busy

def is_turtlebot_ready_at_loading_station() -> bool:
    """
    Verifica se o TurtleBot 4 está pronto.
    Compara a pose real (/odom) com o pickup_point (x: -1.078, y: 0.130).
    Permite bypass se o modo simulado estiver ativo.
    """
    try:
        from backend.api.turtlebot_routes import sim_state
        if sim_state.get("active"):
            return True
    except Exception:
        pass

    try:
        from backend.api.health_routes import ping_host
        if not ping_host("192.168.0.129", timeout_sec=1):
            return False

        from backend.ros2_nodes.turtlebot_node import get_turtlebot_node
        tb_node = get_turtlebot_node()
        st = tb_node.get_status()
        pose = st.get("current_pose", {})
        tx = pose.get("x", 0.0)
        ty = pose.get("y", 0.0)

        import math
        # Coordenadas de carregamento (pickup_point) do waypoints.yaml
        dist = math.sqrt((tx - (-1.078))**2 + (ty - 0.130)**2)
        # Tolerância de 18 cm
        return dist <= 0.18
    except Exception as e:
        print(f"[WARN Bridge] Falha ao validar pose do TurtleBot: {e}")
        return False

def record_detected_class(item_class: str):
    global _last_detection_class
    with _lock:
        _last_detection_class = item_class

def get_last_detected_class() -> Optional[str]:
    with _lock:
        return _last_detection_class
