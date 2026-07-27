# ============================================================
# cobot_routes.py — API Router de Controle do Cobot e Modo Ensino
# ============================================================
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.ros2_nodes.cobot_node import get_cobot_node, REQUIRED_POSES

router = APIRouter(prefix="/api/v1/cobot", tags=["Cobot Control"])

class PumpControlSchema(BaseModel):
    on: bool

class MovePoseSchema(BaseModel):
    velocity_scaling: Optional[float] = 0.20

@router.get("/poses")
def get_poses_status():
    """Retorna a lista de poses gravadas, status de cada pose e data do último salvamento."""
    node = get_cobot_node()
    poses_map = node.poses
    saved_at = poses_map.get("_last_saved", "Nenhum salvamento registrado")
    
    status_list = []
    for p in REQUIRED_POSES:
        recorded = p in poses_map
        status_list.append({
            "name": p,
            "recorded": recorded,
            "joints": poses_map.get(p) if recorded else None
        })
        
    return {
        "last_saved": saved_at,
        "required_poses": REQUIRED_POSES,
        "poses": status_list
    }

@router.post("/move/{pose_name}")
def move_to_pose(pose_name: str, payload: Optional[MovePoseSchema] = None):
    """Move o braço do robô para a pose especificada."""
    node = get_cobot_node()
    vel = payload.velocity_scaling if payload else 0.20
    ok = node.goto_pose(pose_name, velocity_scaling=vel)
    if not ok:
        raise HTTPException(status_code=500, detail=f"Falha ao mover robô para a pose '{pose_name}'.")
    return {"status": "success", "message": f"Chegou na pose '{pose_name}'."}

@router.post("/pump")
def control_pump(payload: PumpControlSchema):
    """Liga (on=true) ou Desliga (on=false) a bomba de sucção."""
    node = get_cobot_node()
    ok = node.set_pump(payload.on)
    if not ok:
        raise HTTPException(status_code=500, detail="Falha no comando da bomba de sucção.")
    return {"status": "success", "pump_active": payload.on}

@router.post("/teach/release")
def release_servos():
    """Liberar os torques dos motores para ensino manual (SEGURE O BRAÇO!)."""
    node = get_cobot_node()
    ok = node.call_trigger_service(node.release_cli, "Liberar Servos")
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao soltar motores.")
    return {"status": "success", "message": "Motores liberados."}

@router.post("/teach/lock")
def lock_servos():
    """Travar os torques dos motores na posição atual."""
    node = get_cobot_node()
    ok = node.call_trigger_service(node.lock_cli, "Travar Servos")
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao travar motores.")
    return {"status": "success", "message": "Motores travados."}

@router.post("/teach/record/{pose_name}")
def record_current_pose(pose_name: str):
    """Grava a posição angular atual do robô na pose especificada em memória."""
    if pose_name not in REQUIRED_POSES:
        raise HTTPException(status_code=400, detail=f"Pose inválida. Deve ser uma de: {REQUIRED_POSES}")
    node = get_cobot_node()
    if node.current_joints is None:
        raise HTTPException(status_code=503, detail="Sem leitura atual de /joint_states do robô.")
    node.poses[pose_name] = [float(v) for v in node.current_joints]
    return {"status": "success", "pose": pose_name, "joints": node.poses[pose_name]}

@router.post("/teach/save")
def save_recorded_poses():
    """Salva todas as poses gravadas no arquivo YAML com timestamp."""
    node = get_cobot_node()
    ok = node.save_poses()
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao salvar arquivo de poses.")
    return {"status": "success", "last_saved": node.poses.get("_last_saved")}

@router.delete("/teach/clear")
def clear_recorded_poses():
    """Apaga todas as poses gravadas e remove o arquivo de calibragem (Zerar calibragem)."""
    node = get_cobot_node()
    ok = node.clear_poses()
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao apagar arquivo de poses.")
    return {"status": "success", "message": "Calibragem zerada com sucesso!"}

@router.post("/teach/playback")
def playback_trajectory():
    """Executa o teste da trajetória completa com acionamento da bomba a 10% de velocidade."""
    node = get_cobot_node()
    missing = [p for p in REQUIRED_POSES if p not in node.poses]
    if missing:
        raise HTTPException(status_code=400, detail=f"Gravação incompleta. Poses pendentes: {missing}")

    sequence_part1 = ["home", "scan", "pick_approach", "pick"]
    for p in sequence_part1:
        if not node.goto_pose(p, velocity_scaling=0.10):
            raise HTTPException(status_code=500, detail=f"Playback falhou na pose {p}.")
            
    node.set_pump(True)
    
    sequence_part2 = ["pick_approach", "home", "place_approach", "place"]
    for p in sequence_part2:
        if not node.goto_pose(p, velocity_scaling=0.10):
            node.set_pump(False)
            raise HTTPException(status_code=500, detail=f"Playback falhou na pose {p}.")
            
    node.set_pump(False)
    
    sequence_part3 = ["place_approach", "home", "scan"]
    for p in sequence_part3:
        if not node.goto_pose(p, velocity_scaling=0.10):
            raise HTTPException(status_code=500, detail=f"Playback falhou na pose {p}.")

    return {"status": "success", "message": "Playback completo com acionamento da bomba finalizado com sucesso!"}
