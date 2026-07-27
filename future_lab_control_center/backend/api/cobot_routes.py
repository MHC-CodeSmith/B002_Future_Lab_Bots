# ============================================================
# cobot_routes.py — API Router de Controle do Cobot e Modo Ensino
# ============================================================
import os
import signal
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.ros2_nodes.cobot_node import get_cobot_node, REQUIRED_POSES

router = APIRouter(prefix="/api/v1/cobot", tags=["Cobot Control"])

# Gerenciamento do Processo de Teste Isolado do YOLO
yolo_process: Optional[subprocess.Popen] = None
yolo_test_active: bool = False

def stop_yolo_test_process():
    """Desativa e encerra o processo de teste isolado do YOLO por segurança."""
    global yolo_process, yolo_test_active
    yolo_test_active = False
    if yolo_process is not None:
        try:
            yolo_process.terminate()
            yolo_process.wait(timeout=2)
        except Exception:
            try:
                yolo_process.kill()
            except Exception:
                pass
        yolo_process = None
    try:
        subprocess.run(["pkill", "-f", "cam_yolo_test.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def start_yolo_test_process():
    """Inicia o script de inspeção do YOLO em background."""
    global yolo_process, yolo_test_active
    stop_yolo_test_process()
    
    possible_paths = [
        Path("/cobot/mycobot_docker/RUN_CAMERA_TEST.sh"),
        Path("/home/future-lab/B002_Future_Lab_Bots/cobot/mycobot_docker/RUN_CAMERA_TEST.sh")
    ]
    
    target_path = None
    for p in possible_paths:
        if p.exists():
            target_path = p
            break
            
    if target_path:
        try:
            cmd = ["bash", str(target_path), "--headless", "--nano"]
            yolo_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            yolo_test_active = True
            return True
        except Exception as e:
            print(f"[WARN] Erro ao disparar RUN_CAMERA_TEST.sh: {e}")
            return False
    return False

class PumpControlSchema(BaseModel):
    on: bool

class YoloTestSchema(BaseModel):
    active: bool

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
    """Move o braço do robô desativando o teste isolado do YOLO por segurança."""
    stop_yolo_test_process()
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

@router.post("/yolo_test")
def toggle_yolo_test(payload: YoloTestSchema):
    """Ativa ou Desativa o Teste Isolado de Classificação do YOLO."""
    if payload.active:
        ok = start_yolo_test_process()
        if not ok:
            raise HTTPException(status_code=500, detail="Falha ao disparar script de teste do YOLO.")
        return {"status": "success", "yolo_test_active": True}
    else:
        stop_yolo_test_process()
        return {"status": "success", "yolo_test_active": False}

@router.get("/yolo_test/status")
def get_yolo_test_status():
    """Retorna se o teste isolado do YOLO está ativo."""
    return {"yolo_test_active": yolo_test_active}

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
    stop_yolo_test_process()  # Trava de segurança: desativa o teste isolado do YOLO
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
