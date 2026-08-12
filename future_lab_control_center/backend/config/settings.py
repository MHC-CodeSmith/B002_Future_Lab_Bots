# ============================================================
# settings.py — Gerenciador Dinâmico de Configurações de Rede
# ============================================================
import os
import socket
from pathlib import Path
from dataclasses import dataclass, asdict

# Carregador simples de .env sem exigir pydantic-settings no SO host
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

def load_env_file():
    if ENV_PATH.exists():
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

load_env_file()

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

import time

_cached_active_ip = None
_last_ip_check_time = 0

def resolve_active_nano_ip() -> str:
    """Detecta automaticamente qual IP da Jetson Nano está respondendo na rede (Wi-Fi 192.168.0.62 ou Cabo 192.168.0.250)."""
    global _cached_active_ip, _last_ip_check_time
    now = time.time()
    if _cached_active_ip and (now - _last_ip_check_time) < 5.0:
        return _cached_active_ip

    env_ip = os.getenv("JETSON_NANO_IP", "192.168.0.62")
    candidates = [env_ip, "192.168.0.62", "192.168.0.250"]
    seen = set()
    ordered_candidates = []
    for ip in candidates:
        if ip and ip not in seen:
            seen.add(ip)
            ordered_candidates.append(ip)

    import subprocess
    active_found = None
    for candidate_ip in ordered_candidates:
        try:
            cmd = ["ping", "-c", "1", "-W", "1", candidate_ip]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                active_found = candidate_ip
                break
        except Exception:
            pass

    _cached_active_ip = active_found or env_ip
    _last_ip_check_time = now
    return _cached_active_ip

def resolve_active_turtlebot_ip() -> str:
    """Detecta automaticamente se o TurtleBot 4 está respondendo no IP padrão (192.168.0.129)."""
    env_ip = os.getenv("TURTLEBOT_IP", "192.168.0.129")
    candidates = ["192.168.0.129", env_ip, "192.168.0.251"]
    seen = set()
    for candidate_ip in candidates:
        if candidate_ip and candidate_ip not in seen:
            seen.add(candidate_ip)
            try:
                cmd = ["ping", "-c", "1", "-W", "1", candidate_ip]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode == 0:
                    return candidate_ip
            except Exception:
                pass
    return "192.168.0.129"

@dataclass
class Settings:
    ROS_DOMAIN_ID: int = int(os.getenv("ROS_DOMAIN_ID", 42))
    RMW_IMPLEMENTATION: str = os.getenv("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")
    
    # 2. Endereços IP dos Robôs e Dispositivos na Rede
    HOST_PC_IP: str = os.getenv("HOST_PC_IP", "192.168.0.204")
    JETSON_NANO_IP: str = resolve_active_nano_ip()
    TURTLEBOT_IP: str = resolve_active_turtlebot_ip()

    # 3. Portas e Streams
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", 8000))
    FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", 3000))
    CAMERA_STREAM_URL: str = os.getenv("CAMERA_STREAM_URL", f"http://{resolve_active_nano_ip()}:8080/stream.mjpg")
    
    DEFAULT_COOLDOWN_SEC: float = float(os.getenv("DEFAULT_COOLDOWN_SEC", 5.0))
    DEFAULT_YOLO_CONF: float = float(os.getenv("DEFAULT_YOLO_CONF", 0.60))
    DEFAULT_VELOCITY_SCALING: float = float(os.getenv("DEFAULT_VELOCITY_SCALING", 0.20))

    def model_dump(self) -> dict:
        return asdict(self)

def get_settings() -> Settings:
    load_env_file()
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
