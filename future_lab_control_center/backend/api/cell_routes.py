# ============================================================
# cell_routes.py — API Router para Controle da Célula e Segurança
# ============================================================
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.ros2_nodes.cobot_node import get_cobot_node

router = APIRouter(prefix="/api/v1/cell", tags=["Cell Control"])

class CellModeSchema(BaseModel):
    mode: str  # "auto" ou "manual"
    cooldown_sec: Optional[float] = 5.0
    yolo_conf: Optional[float] = 0.60

cell_state = {
    "mode": "auto",
    "cooldown_sec": 5.0,
    "yolo_conf": 0.60,
    "manual_authorized": False,
    "status": "idle"
}

@router.get("/status")
def get_cell_status():
    """Retorna o status global da célula automatizada."""
    node = get_cobot_node()
    return {
        "cell": cell_state,
        "current_joints": node.current_joints,
        "pump_active": node.pump_active,
        "last_yolo": node.last_yolo_msg
    }

@router.post("/mode")
def set_cell_mode(payload: CellModeSchema):
    """Altera o modo de operação da célula entre 'auto' e 'manual'."""
    if payload.mode not in ["auto", "manual"]:
        raise HTTPException(status_code=400, detail="Modo deve ser 'auto' ou 'manual'.")
    cell_state["mode"] = payload.mode
    if payload.cooldown_sec is not None:
        cell_state["cooldown_sec"] = max(0.0, payload.cooldown_sec)
    if payload.yolo_conf is not None:
        cell_state["yolo_conf"] = max(0.10, min(1.0, payload.yolo_conf))
    return {"status": "success", "cell": cell_state}

@router.post("/authorize_scan")
def authorize_manual_scan():
    """No modo manual, autoriza a execução da próxima inspeção/scan."""
    if cell_state["mode"] != "manual":
        raise HTTPException(status_code=400, detail="Autorização só é necessária no modo manual.")
    cell_state["manual_authorized"] = True
    return {"status": "success", "message": "Scan autorizado para o próximo ciclo."}

@router.post("/stop")
def emergency_stop():
    """Parada de emergência: desliga bomba e instrui o robô a mover suavemente para HOME."""
    node = get_cobot_node()
    node.set_pump(False)
    cell_state["status"] = "stopped"
    cell_state["manual_authorized"] = False
    
    import threading
    t = threading.Thread(target=node.goto_pose, args=("home", 0.15))
    t.start()
    
    return {
        "status": "emergency_stop_triggered",
        "message": "Parada de emergência acionada. Bomba desligada e retornando o braço para HOME."
    }
