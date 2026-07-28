# ============================================================
# health_routes.py — API Router para Diagnóstico de Rede & Pings
# ============================================================
import time
import threading
import subprocess
import urllib.request
from pathlib import Path
from fastapi import APIRouter, HTTPException
from backend.config.settings import get_settings

router = APIRouter(prefix="/api/v1/health", tags=["Health Check"])

def ping_host(ip: str, timeout_sec: int = 1) -> bool:
    """Executa um ping rápido para verificar presença do IP na rede."""
    if not ip or ip in ["127.0.0.1", "localhost"]:
        return True
    try:
        cmd = ["ping", "-c", "1", "-W", str(timeout_sec), ip]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False

def check_http_stream(url: str, timeout_sec: float = 1.5) -> bool:
    """Verifica se o servidor MJPEG da câmera está respondendo."""
    if not url:
        return False
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.status in [200, 301, 302]
    except Exception:
        return False

@router.get("/")
def get_health_status():
    """Retorna a saúde da rede, pings dos dispositivos e status do stream."""
    settings = get_settings()
    
    nano_ping = ping_host(settings.JETSON_NANO_IP)
    nano_stream = check_http_stream(settings.CAMERA_STREAM_URL)
    turtlebot_ping = ping_host(settings.TURTLEBOT_IP)
    host_ping = ping_host(settings.HOST_PC_IP)

    return {
        "status": "online",
        "ros_domain_id": settings.ROS_DOMAIN_ID,
        "rmw_implementation": settings.RMW_IMPLEMENTATION,
        "devices": {
            "host_pc": {
                "ip": settings.HOST_PC_IP,
                "online": host_ping,
                "label": "Computador Host (PC)"
            },
            "jetson_nano": {
                "ip": settings.JETSON_NANO_IP,
                "online": nano_ping,
                "camera_stream_online": nano_stream,
                "camera_stream_url": settings.CAMERA_STREAM_URL,
                "label": "Jetson Nano (MyCobot Bridge + Câmera)"
            },
            "turtlebot4": {
                "ip": settings.TURTLEBOT_IP,
                "online": turtlebot_ping,
                "label": "TurtleBot 4 (AMR Navegação)"
            }
        }
    }

def _find_nano_camera_script():
    """Localiza o script RUN_NANO_CAMERA.sh no filesystem."""
    possible_scripts = [
        Path("/cobot/mycobot_docker/RUN_NANO_CAMERA.sh"),
        Path("/home/future-lab/B002_Future_Lab_Bots/cobot/mycobot_docker/RUN_NANO_CAMERA.sh")
    ]
    for p in possible_scripts:
        if p.exists():
            return p
    return None

@router.post("/restart_camera")
def restart_camera_stream():
    """Executa a rotina oficial de inicialização RUN_NANO_CAMERA.sh start em segundo plano."""
    try:
        from backend.ros2_nodes.cobot_node import get_cobot_node
        get_cobot_node().clear_yolo_state()
    except Exception:
        pass
    target_script = _find_nano_camera_script()
    if not target_script:
        raise HTTPException(status_code=404, detail="Script RUN_NANO_CAMERA.sh não encontrado.")

    def async_restart():
        try:
            print(f"[INFO] Disparando reinicialização da câmera via {target_script} start...")
            res = subprocess.run(["bash", str(target_script), "start"], timeout=25, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(f"[INFO] Resultado da câmera: {res.stdout}")
        except Exception as e:
            print(f"[WARN] Erro durante inicialização da câmera: {e}")

    t = threading.Thread(target=async_restart, daemon=True)
    t.start()

    return {
        "status": "success",
        "message": "Comando de inicialização da câmera disparado na Jetson Nano. Aguarde ~8 segundos para estabilização."
    }

@router.post("/stop_camera")
def stop_camera_stream():
    """Executa RUN_NANO_CAMERA.sh stop para desligar o servidor MJPEG e encerra o teste YOLO."""
    from backend.api.cobot_routes import stop_yolo_test_process
    stop_yolo_test_process()

    target_script = _find_nano_camera_script()
    if not target_script:
        raise HTTPException(status_code=404, detail="Script RUN_NANO_CAMERA.sh não encontrado.")

    def async_stop():
        try:
            print(f"[INFO] Disparando desligamento da câmera via {target_script} stop...")
            res = subprocess.run(["bash", str(target_script), "stop"], timeout=10, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(f"[INFO] Resultado do stop: {res.stdout}")
        except Exception as e:
            print(f"[WARN] Erro durante desligamento da câmera: {e}")

    t = threading.Thread(target=async_stop, daemon=True)
    t.start()

    return {
        "status": "success",
        "message": "Comando de desligamento da câmera enviado à Jetson Nano."
    }

@router.post("/restart_nano_hardware")
def restart_nano_hardware():
    """Reinicia a ponte de comunicação de hardware ROS 2 (mycobot_hw) na Jetson Nano via SSH."""
    def async_restart_hw():
        try:
            print("[INFO] Reiniciando ponte de hardware na Jetson Nano via SSH com sourcing ROS 2...")
            cmd = "sshpass -p Elephant ssh -o StrictHostKeyChecking=no er@192.168.0.250 'bash -c \"source /opt/ros/galactic/setup.bash && source ~/custom_ws/install/setup.bash && pkill -9 -f mycobot_bridge 2>/dev/null || true; sleep 1; nohup ros2 launch mycobot_hw_interface mycobot_hw.launch.py mock:=False baud:=1000000 > /tmp/hw_bridge.log 2>&1 < /dev/null &\"'"
            res = subprocess.run(cmd, shell=True, timeout=10, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(f"[INFO] Resultado da reinicialização de hardware: {res.stdout}")
        except Exception as e:
            print(f"[WARN] Erro durante reinicialização de hardware do Nano: {e}")

    t = threading.Thread(target=async_restart_hw, daemon=True)
    t.start()

    return {
        "status": "success",
        "message": "Comando de reinicialização de hardware enviado à Jetson Nano. Aguarde ~5 segundos."
    }


