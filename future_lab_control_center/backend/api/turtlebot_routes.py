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
    "export ROS_DISCOVERY_SERVER=\"192.168.0.129:11811;\""
)

TB4_WORKSPACE = "/home/future-lab/B002_Future_Lab_Bots/turtlebot4_jazzy"
INTEGRATION_WORKSPACE = "/home/future-lab/B002_Future_Lab_Bots/integration_cobot_tb4"

class TeleopPayload(BaseModel):
    linear_x: float = 0.0
    angular_z: float = 0.0

@router.get("/status")
def get_turtlebot_status():
    """Retorna o status do TurtleBot 4 (bateria, posição, docking)."""
    node = get_turtlebot_node()
    return node.get_status()

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
        map_path = os.path.join(TB4_WORKSPACE, "maps/B002_map.yaml")
        cmd = f'cd {TB4_WORKSPACE} && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation localization.launch.py map:={map_path}'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Localização Nav2 (B002_map.yaml) iniciada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar Localização: {e}")

@router.post("/launch_nav2")
def launch_nav2():
    """Lança o Stack de Navegação Nav2 com as configurações do projeto."""
    try:
        params_path = os.path.join(TB4_WORKSPACE, "config/nav2_custom.yaml")
        cmd = f'cd {TB4_WORKSPACE} && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation nav2.launch.py params_file:={params_path}'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        return {"status": "success", "message": "Stack Nav2 (nav2_custom.yaml) iniciado com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar Nav2: {e}")

@router.post("/launch_viz")
def launch_viz():
    """Abre a visualização de navegação do Nav2 (view_navigation.launch.py) no monitor do PC Host."""
    try:
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd_viz = f'cd {TB4_WORKSPACE} && export DISPLAY=:0; export XAUTHORITY=/root/.Xauthority; {JAZZY_ENV_CMD} && ros2 launch turtlebot4_viz view_navigation.launch.py'
        _launch_gui_in_pty(cmd_viz)
        return {"status": "success", "message": "Janela do RViz Nav2 disparada no monitor do PC Host!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao abrir RViz Nav2: {e}")

@router.post("/launch_mission_manager")
def launch_mission_manager():
    """Inicializa o Gerenciador de Missões (mission_manager.py)."""
    try:
        cmd = f'cd {TB4_WORKSPACE} && {JAZZY_ENV_CMD} && python3 scripts/mission_manager.py --ros-args --params-file params/waypoints.yaml'
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
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd_3d = f'cd {INTEGRATION_WORKSPACE} && export DISPLAY=:0; export XAUTHORITY=/root/.Xauthority; ./scripts/run_3d_view.sh'
        _launch_gui_in_pty(cmd_3d)
        return {"status": "success", "message": "Janela 3D Integrada (Cobot + TurtleBot 4) disparada no monitor do PC Host!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao abrir Visão 3D Integrada: {e}")
