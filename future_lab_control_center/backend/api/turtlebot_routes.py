# ============================================================
# turtlebot_routes.py — API Router do TurtleBot 4 (AMR & Jazzy Stack)
# ============================================================
import os
import subprocess
import threading
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.ros2_nodes.turtlebot_node import get_turtlebot_node
from backend.api.health_routes import _launch_gui_in_pty

router = APIRouter(prefix="/api/v1/turtlebot", tags=["TurtleBot 4"])

JAZZY_ENV_CMD = (
    "source /opt/ros/jazzy/setup.bash && "
    "export ROS_DOMAIN_ID=0 && "
    "export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET && "
    "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && "
    "export ROS_SUPER_CLIENT=True && "
    "export ROS_DISCOVERY_SERVER=192.168.0.129:11811 && "
    "export DISPLAY=:0 && "
    "export LIBGL_ALWAYS_SOFTWARE=1 && "
    "export QT_X11_NO_MITSHM=1"
)

from pathlib import Path

def get_tb4_workspace() -> str:
    candidates = [
        Path("/app/turtlebot4_jazzy"),
        Path("/home/future-lab/B002_Future_Lab_Bots/turtlebot4_jazzy")
    ]
    p = next((c for c in candidates if c.exists()), candidates[0])
    return str(p)

def get_integration_workspace() -> str:
    candidates = [
        Path("/app/integration_cobot_tb4"),
        Path("/home/future-lab/B002_Future_Lab_Bots/integration_cobot_tb4")
    ]
    p = next((c for c in candidates if c.exists()), candidates[0])
    return str(p)

class TeleopPayload(BaseModel):
    linear_x: float = 0.0
    angular_z: float = 0.0

from backend.api.health_routes import ping_host

@router.get("/status")
def get_turtlebot_status():
    """Retorna o status do TurtleBot 4 (bateria, posição, docking)."""
    tb_ip = "192.168.0.129"
    ping_ok = ping_host(tb_ip, timeout_sec=1)
    node = get_turtlebot_node()
    st = node.get_status()
    st["ping_ok"] = ping_ok
    if not ping_ok:
        st["status"] = "offline"
        st["battery_percentage"] = None
    return st

@router.get("/diagnose")
def diagnose_turtlebot_network():
    """Executa um teste completo de rede (ping) e auditoria de tópicos ROS 2 no Discovery Server do TurtleBot 4."""
    tb_ip = "192.168.0.129"
    ping_ok = ping_host(tb_ip, timeout_sec=2)
    
    topics = []
    key_topics_status = {
        "/scan": False,
        "/odom": False,
        "/cmd_vel": False,
        "/battery_state": False,
        "/tf": False,
        "/robot_description": False
    }
    
    if ping_ok:
        try:
            cmd = f'{JAZZY_ENV_CMD} && ros2 topic list'
            res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                raw_lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                topics = raw_lines
                for t in key_topics_status.keys():
                    key_topics_status[t] = t in raw_lines
        except Exception:
            pass
            
    return {
        "status": "success",
        "ping_ok": ping_ok,
        "tb_ip": tb_ip,
        "topics_count": len(topics),
        "key_topics": key_topics_status,
        "all_topics": topics
    }

@router.get("/logs")
def get_turtlebot_logs(source: str = "all", lines: int = 60):
    """Retorna os últimos logs do console de Localização, Nav2 Stack, RViz2 ou Missões."""
    try:
        log_file_map = {
            "localization": "/tmp/nav2_localization.log",
            "nav2": "/tmp/nav2_stack.log",
            "viz": "/tmp/nav2_viz.log",
            "mission": "/tmp/nav2_mission_manager.log"
        }
        
        target_file = log_file_map.get(source)
        if target_file and os.path.exists(target_file):
            with open(target_file, "r") as f:
                raw = [l.strip() for l in f.readlines() if l.strip()]
                return {"status": "success", "source": source, "logs": raw[-lines:]}
        
        # Se for "all" ou se o arquivo específico ainda não existir, consolida de todos os arquivos ou docker
        consolidated = []
        for src, filepath in log_file_map.items():
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    file_lines = [f"[{src.upper()}] {l.strip()}" for l in f.readlines() if l.strip()]
                    consolidated.extend(file_lines[-20:])
        
        if not consolidated:
            cmd = f"docker logs --tail {lines} future_lab_backend 2>&1"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
            log_text = res.stdout if res.returncode == 0 else "Nenhum log disponível no momento."
            consolidated = [l.strip() for l in log_text.splitlines() if l.strip()]
            
        return {"status": "success", "source": source, "logs": consolidated[-lines:]}
    except Exception as e:
        return {"status": "error", "source": source, "logs": [f"Erro ao ler logs: {e}"]}

@router.post("/teleop")
def send_teleop(payload: TeleopPayload):
    """Envia controle manual de velocidade linear e angular (/cmd_vel)."""
    try:
        node = get_turtlebot_node()
        node.send_cmd_vel(payload.linear_x, payload.angular_z)
        return {"status": "success", "linear_x": payload.linear_x, "angular_z": payload.angular_z}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao enviar teleop: {e}")

@router.post("/dock")
def trigger_dock():
    """Envia o comando de Docking (Ir para Estação de Carga)."""
    tb_ip = "192.168.0.129"
    if not ping_host(tb_ip, timeout_sec=2):
        raise HTTPException(status_code=503, detail=f"TurtleBot 4 (IP {tb_ip}) está desligado ou desconectado da rede Wi-Fi.")
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /dock irobot_create_msgs/action/Dock "{{}}"'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Comando de Docking enviado ao TurtleBot 4!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar Docking: {e}")

@router.post("/undock")
def trigger_undock():
    """Envia o comando de Undocking (Sair da Estação de Carga)."""
    tb_ip = "192.168.0.129"
    if not ping_host(tb_ip, timeout_sec=2):
        raise HTTPException(status_code=503, detail=f"TurtleBot 4 (IP {tb_ip}) está desligado ou desconectado da rede Wi-Fi.")
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /undock irobot_create_msgs/action/Undock "{{}}"'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Comando de Undocking enviado ao TurtleBot 4!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar Undocking: {e}")

@router.post("/launch_localization")
def launch_localization():
    """Lança o módulo de Localização Nav2 com o mapa B002 e bond_timeout=10.0."""
    try:
        tb4_ws = get_tb4_workspace()
        map_path = os.path.join(tb4_ws, "maps/B002_map.yaml")
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd = f'cd {tb4_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation localization.launch.py map:={map_path} bond_timeout:=10.0 > /tmp/nav2_localization.log 2>&1'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Localização Nav2 (B002_map.yaml) iniciada com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar Localização: {e}")

@router.post("/launch_nav2")
def launch_nav2():
    """Lança o Stack de Navegação Nav2 com as configurações do projeto."""
    try:
        tb4_ws = get_tb4_workspace()
        params_path = os.path.join(tb4_ws, "config/nav2_custom.yaml")
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd = f'cd {tb4_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation nav2.launch.py params_file:={params_path} > /tmp/nav2_stack.log 2>&1'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Stack Nav2 (nav2_custom.yaml) iniciado com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar Nav2: {e}")

@router.post("/launch_viz")
def launch_viz():
    """Abre a visualização de navegação do Nav2 (view_navigation.launch.py) no monitor do PC Host."""
    try:
        tb4_ws = get_tb4_workspace()
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd_viz = f'cd {tb4_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_viz view_navigation.launch.py > /tmp/nav2_viz.log 2>&1'
        subprocess.Popen(cmd_viz, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Janela do RViz Nav2 disparada no monitor do PC Host!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao abrir RViz Nav2: {e}")

@router.post("/launch_mission_manager")
def launch_mission_manager():
    """Inicializa o Gerenciador de Missões (mission_manager.py)."""
    try:
        tb4_ws = get_tb4_workspace()
        cmd = f'cd {tb4_ws} && {JAZZY_ENV_CMD} && python3 scripts/mission_manager.py --ros-args --params-file params/waypoints.yaml > /tmp/nav2_mission_manager.log 2>&1'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Nó Mestre do Mission Manager inicializado!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar Mission Manager: {e}")

@router.post("/trigger_delivery")
def trigger_delivery():
    """Aciona o serviço ROS 2 de entrega de peças (/start_delivery)."""
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 service call /start_delivery std_srvs/srv/Trigger {{}}'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Rotina de Entrega (/start_delivery) acionada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar rotina de entrega: {e}")

@router.post("/trigger_failure")
def trigger_failure():
    """Aciona o serviço ROS 2 de recolhimento de peça com defeito / descarte (/start_failure)."""
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 service call /start_failure std_srvs/srv/Trigger {{}}'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Rotina de Falha/Descarte (/start_failure) acionada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar rotina de falha: {e}")

@router.post("/trigger_restock")
def trigger_restock():
    """Aciona o serviço ROS 2 de reabastecimento de matéria-prima (/start_restock)."""
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 service call /start_restock std_srvs/srv/Trigger {{}}'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Rotina de Reabastecimento (/start_restock) acionada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar rotina de reabastecimento: {e}")

@router.post("/trigger_patrol")
def trigger_patrol():
    """Aciona o serviço ROS 2 de ronda/patrulha (/start_patrol)."""
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 service call /start_patrol std_srvs/srv/Trigger {{}}'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Rotina de Patrulha (/start_patrol) acionada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar rotina de patrulha: {e}")

@router.post("/launch_integrated_3d")
def launch_integrated_3d():
    """Abre a cena gráfica 3D integrada (MyCobot 280 + TurtleBot 4 + Mapa B002) no monitor do PC Host."""
    try:
        integration_ws = get_integration_workspace()
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd_3d = f'cd {integration_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && bash ./scripts/run_3d_view.sh'
        subprocess.Popen(cmd_3d, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Janela 3D Integrada (Cobot + TurtleBot 4) disparada no monitor do PC Host!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao abrir Visão 3D Integrada: {e}")

@router.post("/start_oakd_camera")
def start_oakd_camera():
    """Desperta a câmera OAK-D-PRO no TurtleBot 4 chamando o serviço ROS 2 /oakd/start_camera."""
    tb_ip = "192.168.0.129"
    if not ping_host(tb_ip, timeout_sec=2):
        raise HTTPException(status_code=503, detail=f"TurtleBot 4 (IP {tb_ip}) não acessível na rede.")
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 service call /oakd/start_camera std_srvs/srv/Trigger {{}}'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {
            "status": "success",
            "message": "Câmera OAK-D-PRO despertada e ativada no TurtleBot 4 com sucesso!",
            "stream_url": "/api/v1/turtlebot/oakd_stream"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar câmera OAK-D: {e}")

from fastapi.responses import StreamingResponse

@router.get("/oakd_stream")
def proxy_oakd_stream():
    """Streaming MJPEG ao vivo da Câmera OAK-D-PRO do TurtleBot 4."""
    node = get_turtlebot_node()

    def generate_frames():
        while True:
            frame = node.latest_jpeg_frame
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                time.sleep(0.04)  # ~25 FPS
            else:
                time.sleep(0.1)

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
