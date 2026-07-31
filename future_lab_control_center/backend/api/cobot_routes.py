# ============================================================
# cobot_routes.py — API Router de Controle do Cobot e Modo Ensino
# ============================================================
import os
import time
import signal
import threading
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
    """Desativa e encerra o processo de teste isolado do YOLO de forma direta e sem race condition, fechando a janela gráfica."""
    global yolo_process, yolo_test_active
    yolo_test_active = False
    try:
        from backend.ros2_nodes.cobot_node import get_cobot_node
        get_cobot_node().clear_yolo_state()
    except Exception:
        pass
    proc = yolo_process
    yolo_process = None
    if proc is not None:
        try:
            proc.kill()
            proc.wait(timeout=0.5)
        except Exception:
            pass
    try:
        subprocess.run("docker exec mycobot_ros2 pkill -9 -f cam_yolo_test 2>/dev/null || true", shell=True, timeout=2)
        subprocess.run("pkill -9 -f cam_yolo_test 2>/dev/null || true", shell=True, timeout=2)
    except Exception:
        pass

_yolo_log_file = None

def start_yolo_test_process(conf: float = 0.60, headless: bool = True) -> bool:
    """Dispara o processo cam_yolo_test.py em background enviando o log para /tmp/yolo_test.log."""
    global yolo_process, yolo_test_active, _yolo_log_file
    stop_yolo_test_process()  # Garante limpo
    
    possible_scripts = [
        Path("/cobot/mycobot_docker/custom_ws/scripts/cam_yolo_test.py"),
        Path("/home/future-lab/B002_Future_Lab_Bots/cobot/mycobot_docker/custom_ws/scripts/cam_yolo_test.py"),
        Path("/app/cobot/cam_yolo_test.py"),
        Path(__file__).resolve().parent.parent.parent.parent / "cobot" / "cam_yolo_test.py"
    ]
    
    target_script = None
    for p in possible_scripts:
        if p.exists():
            target_script = p
            break
            
    if target_script:
        try:
            if _yolo_log_file is not None:
                try:
                    _yolo_log_file.close()
                except Exception:
                    pass
            _yolo_log_file = open("/tmp/yolo_test.log", "a")
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = "/opt/ros/jazzy/lib:" + env.get("LD_LIBRARY_PATH", "")
            env["PYTHONPATH"] = "/opt/ros/jazzy/lib/python3.12/site-packages:" + env.get("PYTHONPATH", "")
            env["PYTHONUNBUFFERED"] = "1"
            
            from backend.config.settings import get_settings
            stream_url = get_settings().CAMERA_STREAM_URL

            cmd = [
                "python3", "-u",
                str(target_script),
                "--headless",
                "--conf", str(conf),
                "--url", stream_url
            ]
            yolo_process = subprocess.Popen(cmd, env=env, stdout=_yolo_log_file, stderr=_yolo_log_file)
            yolo_test_active = True
            print(f"[INFO] Processo cam_yolo_test.py iniciado com SUCESSO (PID {yolo_process.pid}) na URL {stream_url}")
            return True
        except Exception as e:
            print(f"[WARN] Erro ao disparar cam_yolo_test.py: {e}")
            return False
    return False

_last_pgrep_time = 0.0
_cached_alive = False

def is_yolo_process_alive():
    """Verifica se o processo python3 cam_yolo_test.py está ativo no SO sem falso-positivos e com cache de 500ms."""
    global yolo_process, yolo_test_active, _last_pgrep_time, _cached_alive
    now = time.time()
    if yolo_process is not None:
        poll = yolo_process.poll()
        if poll is None:
            yolo_test_active = True
            _cached_alive = True
            return True
        else:
            yolo_process = None

    if (now - _last_pgrep_time) < 0.5:
        return _cached_alive

    _last_pgrep_time = now
    try:
        res = subprocess.run(["pgrep", "-f", "python3.*cam_yolo_test.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _cached_alive = (res.returncode == 0 and len(res.stdout.strip()) > 0)
        yolo_test_active = _cached_alive
        return _cached_alive
    except Exception:
        yolo_test_active = False
        _cached_alive = False
        return False

class PumpControlSchema(BaseModel):
    on: bool

class YoloTestSchema(BaseModel):
    active: bool

class MovePoseSchema(BaseModel):
    velocity_scaling: Optional[float] = 0.20

@router.get("/poses")
def get_poses_status():
    """Retorna a lista de poses gravadas em memória, status de cada pose e data do último salvamento."""
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
        "has_backup": node.has_backup_poses(),
        "required_poses": REQUIRED_POSES,
        "playback_status": playback_control.get("status", "idle"),
        "poses": status_list
    }

@router.post("/move/{pose_name}")
def move_to_pose(pose_name: str, payload: Optional[MovePoseSchema] = None):
    """Move o braço do robô desativando o teste isolado do YOLO por segurança."""
    from backend.api.cell_routes import cell_state
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em modo de Pânico. É necessário reiniciar o sistema.")
    if cell_state.get("auto_running"):
        raise HTTPException(status_code=400, detail="Movimentação de calibragem bloqueada enquanto o Modo Automático estiver em execução!")

    stop_yolo_test_process()
    node = get_cobot_node()
    default_vel = float(cell_state.get("arm_speed", 0.15))
    vel = payload.velocity_scaling if (payload and payload.velocity_scaling is not None) else default_vel
    vel = max(0.01, min(0.15, vel))
    ok = node.goto_pose(pose_name, velocity_scaling=vel)
    if not ok:
        raise HTTPException(status_code=500, detail=f"Falha ao mover robô para a pose '{pose_name}'.")
    return {"status": "success", "message": f"Chegou na pose '{pose_name}' com velocidade {vel*100:.0f}%."}

@router.post("/pump")
def control_pump(payload: PumpControlSchema):
    """Liga (on=true) ou Desliga (on=false) a bomba de sucção."""
    from backend.api.cell_routes import cell_state
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em modo de Pânico. É necessário reiniciar o sistema.")
    node = get_cobot_node()
    ok = node.set_pump(payload.on)
    if not ok:
        raise HTTPException(status_code=500, detail="Falha no comando da bomba de sucção.")
    return {"status": "success", "pump_active": payload.on}

@router.post("/yolo_test")
def toggle_yolo_test(payload: YoloTestSchema):
    """Ativa ou Desativa o Teste Isolado de Classificação do YOLO."""
    from backend.api.cell_routes import cell_state
    if payload.active and cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em modo de Pânico. É necessário reiniciar o sistema.")
    if payload.active:
        conf = float(cell_state.get("yolo_conf", 0.25))
        ok = start_yolo_test_process(conf=conf)
        if not ok:
            raise HTTPException(status_code=500, detail="Falha ao disparar script de teste do YOLO.")
        return {"status": "success", "yolo_test_active": True}
    else:
        stop_yolo_test_process()
        return {"status": "success", "yolo_test_active": False}

@router.get("/yolo_test/status")
def get_yolo_test_status():
    """Retorna se o teste isolado do YOLO está ativo (verifica se o processo está vivo)."""
    alive = is_yolo_process_alive()
    return {"yolo_test_active": alive}

@router.post("/teach/release")
def release_servos():
    """Liberar os torques dos motores para ensino manual (SEGURE O BRAÇO!)."""
    from backend.api.cell_routes import cell_state
    if cell_state.get("auto_running"):
        raise HTTPException(status_code=400, detail="Operação de calibragem bloqueada enquanto o Modo Automático estiver em execução!")
    node = get_cobot_node()
    ok = node.call_trigger_service(node.release_cli, "Liberar Servos")
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao soltar motores.")
    return {"status": "success", "message": "Motores liberados."}

@router.post("/teach/lock")
def lock_servos():
    """Travar os torques dos motores na posição atual."""
    from backend.api.cell_routes import cell_state
    if cell_state.get("auto_running"):
        raise HTTPException(status_code=400, detail="Operação de calibragem bloqueada enquanto o Modo Automático estiver em execução!")
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
    
    # 1. Tenta obter os ângulos instantâneos direto da Micro-Bridge HTTP do Nano (< 5ms)
    joints_to_record = None
    try:
        import urllib.request
        import json
        from backend.config.settings import get_settings
        nano_ip = get_settings().JETSON_NANO_IP
        req = urllib.request.Request(f"http://{nano_ip}:8088/get_angles")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                if data.get("success") and data.get("joints") and len(data["joints"]) >= 6:
                    joints_to_record = [float(v) for v in data["joints"][:6]]
    except Exception as e:
        print(f"[WARN] HTTP get_angles indisponível ({e}), tentando leitura DDS...")

    # 2. Fallback via leitura DDS /joint_states
    if joints_to_record is None:
        if node.current_joints is not None and len(node.current_joints) >= 6:
            joints_to_record = [float(v) for v in node.current_joints[:6]]

    if joints_to_record is None:
        raise HTTPException(status_code=503, detail="Sem leitura atual de /joint_states ou Micro-Bridge do robô.")

    # Atualiza em memória
    node.poses[pose_name] = joints_to_record
    print(f"[INFO] Pose '{pose_name}' gravada com SUCESSO em memória: {joints_to_record}")
    return {"status": "success", "pose": pose_name, "joints": joints_to_record}

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
    """Cria um backup (.yaml.bak) das últimas poses salvas antes de zerar a calibragem ativa."""
    node = get_cobot_node()
    ok = node.clear_poses()
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao apagar arquivo de poses.")
    return {"status": "success", "message": "Calibragem zerada com sucesso! Backup da versão anterior salvo."}

@router.post("/teach/restore")
def restore_recorded_poses():
    """Restaura a última calibragem salva a partir do arquivo de backup (.yaml.bak)."""
    node = get_cobot_node()
    if not node.has_backup_poses():
        raise HTTPException(status_code=404, detail="Nenhum backup da calibragem anterior foi encontrado para restaurar.")
    
    ok = node.restore_backup_poses()
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao restaurar o backup de calibragem.")
    return {"status": "success", "message": "Última calibragem restaurada com sucesso!"}

playback_control = {
    "status": "idle",   # "idle", "running", "paused"
    "paused": False,
    "cancel": False
}

def _playback_worker():
    from backend.api.cell_routes import cell_state
    cell_state["status"] = "busy"
    playback_control["status"] = "running"
    playback_control["paused"] = False
    playback_control["cancel"] = False
    node = get_cobot_node()
    try:
        trajectory = [
            "home", "scan", "pick_approach", "pick",
            "pick_approach", "home", "place_approach", "place",
            "place_approach", "home", "scan"
        ]
        for p in trajectory:
            # Trava de pausa/cancelamento antes de iniciar a movimentação para a próxima pose
            while playback_control["paused"]:
                if playback_control["cancel"]:
                    break
                time.sleep(0.1)

            if playback_control["cancel"]:
                print("[INFO] Playback cancelado pelo usuário.")
                break

            print(f"[INFO] Trajetória Playback: Movendo para pose '{p}'...")
            if not node.goto_pose(p, velocity_scaling=0.10):
                node.set_pump(False)
                break

            # Trava de pausa/cancelamento após a chegada na pose
            while playback_control["paused"]:
                if playback_control["cancel"]:
                    break
                time.sleep(0.1)

            if playback_control["cancel"]:
                break

            time.sleep(0.5)

        cell_state["status"] = "idle"
        playback_control["status"] = "idle"
        playback_control["paused"] = False
        playback_control["cancel"] = False
        print("[INFO] Trajetória de Playback finalizada.")
    except Exception as e:
        print(f"[WARN] Erro durante worker de playback: {e}")
        node.set_pump(False)
        cell_state["status"] = "idle"
        playback_control["status"] = "idle"
        playback_control["paused"] = False
        playback_control["cancel"] = False

@router.post("/teach/playback")
def playback_trajectory():
    """Inicia, Pausa ou Retoma o Playback da trajetória sem interferir na câmera nem na bomba."""
    from backend.api.cell_routes import cell_state

    # 1. Se estiver RODANDO -> PAUSA (sem tocar na bomba nem na câmera)
    if playback_control["status"] == "running":
        playback_control["paused"] = True
        playback_control["status"] = "paused"
        print("[INFO] PLAYBACK PAUSADO (Câmera e Bomba mantidas intactas).")
        return {
            "status": "paused",
            "playback_status": "paused",
            "message": "Playback pausado com sucesso!"
        }

    # 2. Se estiver PAUSADO -> RETOMA (continua o movimento)
    if playback_control["status"] == "paused":
        playback_control["paused"] = False
        playback_control["status"] = "running"
        print("[INFO] PLAYBACK RETOMADO.")
        return {
            "status": "resumed",
            "playback_status": "running",
            "message": "Playback retomado com sucesso!"
        }

    # 3. Se estiver IDLE -> INICIA UM NOVO PLAYBACK
    node = get_cobot_node()
    node.load_poses()  # Recarrega as poses salvas do disco antes de validar
    missing = [p for p in REQUIRED_POSES if p not in node.poses]
    if missing:
        raise HTTPException(status_code=400, detail=f"Gravação incompleta. Poses pendentes: {missing}")

    if cell_state.get("status") == "busy":
        raise HTTPException(status_code=409, detail="A célula já está executando uma trajetória.")

    # NOTA: Ao INICIAR novo playback, não desligamos a câmera se o usuário quiser mantê-la ativa
    thread = threading.Thread(target=_playback_worker, daemon=True)
    thread.start()

    return {
        "status": "started",
        "playback_status": "running",
        "message": "Playback da trajetória iniciado com sucesso!"
    }

@router.post("/launch_yolo_window")
def launch_yolo_window():
    """Abre uma janela gráfica nativa OpenCV no monitor do PC Host com visões YOLO, bounding boxes e FPS ao vivo."""
    from backend.api.cell_routes import cell_state
    from backend.config.settings import get_settings
    from backend.api.health_routes import _launch_gui_in_pty
    conf = float(cell_state.get("yolo_conf", 0.60))
    nano_ip = get_settings().JETSON_NANO_IP
    try:
        print(f"[INFO] Disparando janela gráfica nativa OpenCV (cam_yolo_test.py) no monitor do PC Host (DISPLAY=:0 via PTY, Nano IP {nano_ip})...")
        subprocess.run("docker cp /home/future-lab/.Xauthority mycobot_ros2:/root/.Xauthority 2>/dev/null || true", shell=True, timeout=3)
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd_yolo_gui = f'docker exec -t mycobot_ros2 bash -c "export DISPLAY=:0; export XAUTHORITY=/root/.Xauthority; pkill -9 -f cam_yolo_test 2>/dev/null || true; sleep 0.5; python3 /root/custom_ws/scripts/cam_yolo_test.py --url http://{nano_ip}:8080/stream.mjpg --conf {conf}"'
        _launch_gui_in_pty(cmd_yolo_gui)
        return {
            "status": "success",
            "message": "Janela gráfica OpenCV do YOLO disparada no monitor do PC Host com sucesso!"
        }
    except Exception as e:
        print(f"[WARN] Erro ao disparar janela OpenCV do YOLO: {e}")
        raise HTTPException(status_code=500, detail=f"Falha ao abrir janela OpenCV: {e}")
