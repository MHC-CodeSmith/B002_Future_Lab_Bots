# ============================================================
# cell_routes.py — API Router para Controle da Célula e Segurança
# ============================================================
import threading
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
    from backend.api.cobot_routes import is_yolo_process_alive
    return {
        "cell": cell_state,
        "current_joints": node.current_joints,
        "pump_active": node.pump_active,
        "yolo_test_active": is_yolo_process_alive(),
        "last_yolo": node.last_yolo_msg
    }

@router.post("/mode")
def set_cell_mode(payload: CellModeSchema):
    """Altera o modo de operação da célula e atualiza as configurações mestre."""
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
    """Parada de emergência: desliga bomba, desativa teste YOLO e move braço para HOME."""
    node = get_cobot_node()
    if "home" not in node.poses:
        raise HTTPException(
            status_code=400,
            detail="A pose 'home' ainda não foi salva no disco! Grave e salve a pose 'home' antes de acionar o retorno de emergência."
        )

    from backend.api.cobot_routes import stop_yolo_test_process
    stop_yolo_test_process()
    node.set_pump(False)
    cell_state["status"] = "stopped"
    cell_state["manual_authorized"] = False
    
    t = threading.Thread(target=node.goto_pose, args=("home", 0.15))
    t.start()
    
    return {
        "status": "emergency_stop_triggered",
        "message": "Parada de emergência acionada. Bomba e teste YOLO desligados e retornando o braço para HOME."
    }

@router.post("/panic")
def panic_stop():
    """Botão de Pânico Master: cancela o planejamento, para todos os processos, desliga a bomba e trava as juntas do robô imediatamente."""
    from backend.api.cobot_routes import stop_yolo_test_process
    stop_yolo_test_process()
    node = get_cobot_node()
    node.set_pump(False)
    
    # Trava os motores do robô imediatamente
    try:
        node.call_trigger_service(node.lock_cli, "Travar Servos (Pânico)")
    except Exception as e:
        print(f"[WARN] Erro ao travar motores no Pânico: {e}")
        
    cell_state["status"] = "panic_stopped"
    cell_state["manual_authorized"] = False
    
    return {
        "status": "panic_triggered",
        "message": "PÂNICO ACIONADO: Todos os processos interrompidos, motores travados e planejamento cancelado!"
    }

