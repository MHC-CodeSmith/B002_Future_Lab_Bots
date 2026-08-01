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
    "export ROS_DISCOVERY_SERVER=192.168.0.129:11811"
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
    node = get_turtlebot_node()
    return node.get_status()

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
                for k in key_topics_status.keys():
                    key_topics_status[k] = (k in raw_lines)
        except Exception as e:
            print(f"[WARN] Erro ao listar tópicos ROS 2 do TurtleBot: {e}")
            
    return {
        "ping_ok": ping_ok,
        "ip": tb_ip,
        "discovery_server": "192.168.0.129:11811",
        "domain_id": 0,
        "topics_count": len(topics),
        "key_topics": key_topics_status,
        "raw_topics": topics[:25]
    }

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
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /dock irobot_create_msgs/action/Dock "{{}}"'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        node = get_turtlebot_node()
        node.is_docked = True
        return {"status": "success", "message": "Comando de Docking enviado ao TurtleBot 4!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar Docking: {e}")

@router.post("/undock")
def trigger_undock():
    """Envia o comando de Undocking (Sair da Estação de Carga)."""
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /undock irobot_create_msgs/action/Undock "{{}}"'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        node = get_turtlebot_node()
        node.is_docked = False
        return {"status": "success", "message": "Comando de Undocking enviado ao TurtleBot 4!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar Undocking: {e}")

@router.post("/launch_localization")
def launch_localization():
    """Lança o módulo de Localização Nav2 com o mapa B002."""
    try:
        tb4_ws = get_tb4_workspace()
        map_path = os.path.join(tb4_ws, "maps/B002_map.yaml")
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd = f'cd {tb4_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation localization.launch.py map:={map_path}'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Localização Nav2 (B002_map.yaml) iniciada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar Localização: {e}")

@router.post("/launch_nav2")
def launch_nav2():
    """Lança o Stack de Navegação Nav2 com as configurações do projeto."""
    try:
        tb4_ws = get_tb4_workspace()
        params_path = os.path.join(tb4_ws, "config/nav2_custom.yaml")
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd = f'cd {tb4_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation nav2.launch.py params_file:={params_path}'
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
        cmd_viz = f'cd {tb4_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_viz view_navigation.launch.py'
        subprocess.Popen(cmd_viz, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Janela do RViz Nav2 disparada no monitor do PC Host!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao abrir RViz Nav2: {e}")

@router.post("/launch_mission_manager")
def launch_mission_manager():
    """Inicializa o Gerenciador de Missões (mission_manager.py)."""
    try:
        tb4_ws = get_tb4_workspace()
        cmd = f'cd {tb4_ws} && {JAZZY_ENV_CMD} && python3 scripts/mission_manager.py --ros-args --params-file params/waypoints.yaml'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Gerenciador de Missões (mission_manager.py) iniciado com sucesso!"}
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
