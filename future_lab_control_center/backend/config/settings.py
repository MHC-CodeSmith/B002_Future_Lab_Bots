# ============================================================
# settings.py — Gerenciador Dinâmico de Configurações de Rede
# ============================================================
import os
import socket
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

def get_auto_ip() -> str:
    """Detecta automaticamente o IP primário da máquina na rede local."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class Settings(BaseSettings):
    ROS_DOMAIN_ID: int = int(os.getenv("ROS_DOMAIN_ID", 42))
    RMW_IMPLEMENTATION: str = os.getenv("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")
    
    HOST_PC_IP: str = os.getenv("HOST_PC_IP", get_auto_ip())
    JETSON_NANO_IP: str = os.getenv("JETSON_NANO_IP", "192.168.0.250")
    TURTLEBOT_IP: str = os.getenv("TURTLEBOT_IP", "192.168.0.251")
    
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", 8000))
    FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", 3000))
    CAMERA_STREAM_URL: str = os.getenv("CAMERA_STREAM_URL", f"http://192.168.0.250:8080/stream.mjpg")
    
    DEFAULT_COOLDOWN_SEC: float = float(os.getenv("DEFAULT_COOLDOWN_SEC", 5.0))
    DEFAULT_YOLO_CONF: float = float(os.getenv("DEFAULT_YOLO_CONF", 0.60))
    DEFAULT_VELOCITY_SCALING: float = float(os.getenv("DEFAULT_VELOCITY_SCALING", 0.20))

    class Config:
        env_file = ".env"
        extra = "ignore"

def get_settings() -> Settings:
    return Settings()

def update_env_file(new_data: dict) -> bool:
    """Atualiza o arquivo .env dinamicamente no disco."""
    try:
        lines = []
        if ENV_PATH.exists():
            with open(ENV_PATH, "r") as f:
                lines = f.readlines()
        
        current_map = {}
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                current_map[k] = v

        for k, v in new_data.items():
            current_map[k.upper()] = str(v)

        with open(ENV_PATH, "w") as f:
            f.write("# ====================================================\n")
            f.write("# Future Lab Control Center — Network Settings\n")
            f.write("# ====================================================\n")
            for k, v in current_map.items():
                f.write(f"{k}={v}\n")
        return True
    except Exception as e:
        print(f"Erro ao salvar .env: {e}")
        return False
