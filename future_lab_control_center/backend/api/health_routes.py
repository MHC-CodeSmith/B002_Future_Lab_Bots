# ============================================================
# health_routes.py — API Router para Diagnóstico de Rede & Pings
# ============================================================
import subprocess
import urllib.request
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
    """Tenta reiniciar o serviço de câmera e stream no Nano via SSH."""
    settings = get_settings()
    try:
        ssh_cmd = [
            "sshpass", "-p", "Elephant",
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
            f"er@{settings.JETSON_NANO_IP}",
            "pkill -f cam_yolo_test.py || true; nohup python3 /home/er/cam_yolo_test.py > /dev/null 2>&1 &"
        ]
        subprocess.run(ssh_cmd, timeout=5)
        return {"status": "success", "message": "Comando de reinicialização da câmera enviado para a Jetson Nano."}
    except Exception as e:
        return {"status": "warning", "message": f"Stream local atualizado. ({e})"}
