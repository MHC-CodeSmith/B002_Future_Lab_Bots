# ============================================================
# turtlebot_routes.py — API Router do TurtleBot 4 (Skeleton)
# ============================================================
from fastapi import APIRouter
from backend.ros2_nodes.turtlebot_node import get_turtlebot_node

router = APIRouter(prefix="/api/v1/turtlebot", tags=["TurtleBot 4"])

@router.get("/status")
def get_turtlebot_status():
    """Retorna o status do TurtleBot 4 (bateria, posição, docking)."""
    node = get_turtlebot_node()
    return node.get_status()
