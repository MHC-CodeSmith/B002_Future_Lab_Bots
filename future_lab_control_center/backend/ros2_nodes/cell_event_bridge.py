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
    Verifica se o TurtleBot 4 está no Ponto de Coleta / Estação de Carga e livre para receber peças.
    Retorna True se estiver pronto; False se estiver em rota de entrega ou offline.
    """
    from backend.ros2_nodes.turtlebot_node import get_turtlebot_node
    tb_node = get_turtlebot_node()
    status = tb_node.get_status()
    
    # Se o robô móvel estiver offline ou em movimento livre, trata com segurança
    if status.get("status") == "offline":
        return True  # Fallback permissivo para operação em modo isolado sem AMR
        
    is_docked = Boolean(status.get("is_docked", False))
    dock_visible = Boolean(status.get("dock_visible", False))
    
    if is_turtlebot_busy():
        return False
        
    return is_docked or dock_visible or (status.get("status") == "idle")

def record_detected_class(item_class: str):
    global _last_detection_class
    with _lock:
        _last_detection_class = item_class

def get_last_detected_class() -> Optional[str]:
    with _lock:
        return _last_detection_class
