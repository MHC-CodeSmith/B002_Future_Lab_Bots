# ============================================================
# health_routes.py — API Router para Diagnóstico de Rede & Pings
# ============================================================
import time
import subprocess
import urllib.request
from pathlib import Path
from fastapi import APIRouter
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

@router.post("/restart_camera")
def restart_camera_stream():
    """Executa a rotina idêntica ao RUN_NANO_CAMERA.sh start via SSH no Nano."""
    settings = get_settings()
    nano_ip = settings.JETSON_NANO_IP
    script_path = Path("/home/future-lab/B002_Future_Lab_Bots/cobot/mycobot_docker/nano_camera_server.py")
    
    try:
        if script_path.exists():
            scp_cmd = [
                "sshpass", "-p", "Elephant", "scp",
                "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
                str(script_path), f"er@{nano_ip}:~/nano_camera_server.py"
            ]
            subprocess.run(scp_cmd, timeout=5)

        kill_cmd = [
            "sshpass", "-p", "Elephant", "ssh",
            "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
            f"er@{nano_ip}", "pkill -9 -f nano_camera_server.py 2>/dev/null || true"
        ]
        subprocess.run(kill_cmd, timeout=5)

        time.sleep(1.0)

        start_cmd = [
            "sshpass", "-p", "Elephant", "ssh",
            "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
            f"er@{nano_ip}", "nohup python3 -u /home/er/nano_camera_server.py --device 0 --port 8080 > /tmp/camera.log 2>&1 &"
        ]
        subprocess.run(start_cmd, timeout=5)
        return {"status": "success", "message": "Servidor MJPEG da câmera iniciado com sucesso na Jetson Nano!"}
    except Exception as e:
        return {"status": "error", "message": f"Falha ao enviar comando SSH para o Nano: {e}"}
