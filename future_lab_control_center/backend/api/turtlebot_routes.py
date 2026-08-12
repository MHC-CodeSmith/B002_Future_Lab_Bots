# ============================================================
# turtlebot_routes.py — API Router do TurtleBot 4 (AMR & Jazzy Stack)
# ============================================================
import os
import time
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
    "export FASTDDS_BUILTIN_TRANSPORTS=UDPv4 && "
    "export ROS_SUPER_CLIENT=True && "
    'export ROS_DISCOVERY_SERVER="192.168.0.129:11811;" && '
    "export DISPLAY=:0 && "
    "export LIBGL_ALWAYS_SOFTWARE=1 && "
    "export QT_X11_NO_MITSHM=1"
)

JAZZY_ENV_CMD_DS = JAZZY_ENV_CMD

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

class SimulationStartSchema(BaseModel):
    item: str = "blue"  # "blue" ou "red"

sim_state = {
    "active": False,
    "selected_item": "blue",
    "current_step": "idle",
    "step_index": 0,
    "step_title": "Simulação Inativa",
    "step_description": "Selecione a peça e inicie o modo simulado.",
    "waiting_confirmation": False,
    "busy": False
}

@router.get("/status")
def get_turtlebot_status():
    """Retorna o status do TurtleBot 4 (bateria, posição, docking e modo simulado)."""
    tb_ip = "192.168.0.129"
    ping_ok = ping_host(tb_ip, timeout_sec=1)
    node = get_turtlebot_node()
    st = node.get_status()
    st["ping_ok"] = ping_ok
    if not ping_ok:
        st["status"] = "offline"
        st["battery_percentage"] = None
    st["sim_state"] = sim_state
    return st

@router.post("/simulation/start")
def start_simulation(payload: SimulationStartSchema):
    node = get_turtlebot_node()
    st = node.get_status()
    is_docked = bool(st.get("is_docked", False))
    
    sim_state["active"] = True
    sim_state["selected_item"] = payload.item
    sim_state["busy"] = True

    # Pré-requisito: Se estiver fora da dock, força o retorno para a dock primeiro!
    if not is_docked:
        sim_state["current_step"] = "returning_dock_prereq"
        sim_state["step_index"] = 1
        sim_state["step_title"] = "Retornando à Estação de Carga (Pré-requisito)"
        sim_state["step_description"] = "O robô está fora da dock. Navegando até a Dock Station antes de iniciar a simulação..."
        sim_state["waiting_confirmation"] = False

        def _run_prereq_dock():
            trigger_dock()
            time.sleep(8.0)
            sim_state["current_step"] = "at_dock"
            sim_state["step_index"] = 2
            sim_state["step_title"] = "Robô na Estação de Carga (Pronto)"
            sim_state["step_description"] = f"Robô acoplado na dock. Peça selecionada: {payload.item.upper()}. Clique em 'CONFIRMAR E IR PARA O PRÓXIMO PASSO' para iniciar o Undock."
            sim_state["waiting_confirmation"] = True
            sim_state["busy"] = False

        threading.Thread(target=_run_prereq_dock, daemon=True).start()
        return {"status": "success", "message": "Pré-requisito iniciado: Retornando robô à Dock Station..."}

    # Se já estiver na dock:
    sim_state["current_step"] = "at_dock"
    sim_state["step_index"] = 1
    sim_state["step_title"] = "Robô na Estação de Carga (Pronto)"
    sim_state["step_description"] = f"Robô acoplado na dock. Peça selecionada: {payload.item.upper()}. Clique em 'CONFIRMAR E IR PARA O PRÓXIMO PASSO' para iniciar o Undock."
    sim_state["waiting_confirmation"] = True
    sim_state["busy"] = False
    return {"status": "success", "message": "Simulação iniciada na Dock Station com sucesso!"}

@router.post("/simulation/next_step")
def next_simulation_step():
    if not sim_state["active"]:
        raise HTTPException(status_code=400, detail="Simulação não está ativa.")

    if sim_state["busy"]:
        return {"status": "busy", "message": "Robô em movimento. Aguarde a conclusão do trajeto atual."}

    step = sim_state["current_step"]
    item = sim_state["selected_item"]

    if step == "at_dock":
        # Passo 2: Undock & Ir para Ponto de Coleta (pickup_point)
        sim_state["current_step"] = "going_pickup"
        sim_state["step_index"] = 2
        sim_state["step_title"] = "Undock & Indo para Ponto de Coleta"
        sim_state["step_description"] = "Desengatando da dock e navegando até 'pickup_point'..."
        sim_state["waiting_confirmation"] = False
        sim_state["busy"] = True

        def _step_pickup():
            trigger_undock()
            time.sleep(4.0)
            cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{{pose: {{header: {{frame_id: map}}, pose: {{position: {{x: -1.078, y: 0.130, z: 0.0}}, orientation: {{w: 1.0}}}}}}}}"'
            subprocess.Popen(cmd, shell=True, executable="/bin/bash")
            time.sleep(12.0)
            sim_state["current_step"] = "at_pickup"
            sim_state["step_index"] = 3
            sim_state["step_title"] = "Chegou ao Ponto de Coleta (pickup_point)"
            sim_state["step_description"] = f"Robô posicionado no Ponto de Coleta. Clique em 'CONFIRMAR E IR PARA O PRÓXIMO PASSO' para navegar até a estação de entrega ({'Azul' if item=='blue' else 'Vermelha'})."
            sim_state["waiting_confirmation"] = True
            sim_state["busy"] = False

        threading.Thread(target=_step_pickup, daemon=True).start()
        return {"status": "success", "message": "Avançando para o Ponto de Coleta..."}

    elif step == "at_pickup":
        # Passo 3: Ir para Estação de Entrega (delivery_blue ou delivery_red)
        target_wp = "delivery_blue" if item == "blue" else "delivery_red"
        target_x = 0.50 if item == "blue" else -0.50
        target_y = 1.20 if item == "blue" else 1.20

        sim_state["current_step"] = "going_delivery"
        sim_state["step_index"] = 4
        sim_state["step_title"] = f"Indo para Estação de Entrega ({item.upper()})"
        sim_state["step_description"] = f"Navegando até o destino '{target_wp}'..."
        sim_state["waiting_confirmation"] = False
        sim_state["busy"] = True

        def _step_delivery():
            cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{{pose: {{header: {{frame_id: map}}, pose: {{position: {{x: {target_x}, y: {target_y}, z: 0.0}}, orientation: {{w: 1.0}}}}}}}}"'
            subprocess.Popen(cmd, shell=True, executable="/bin/bash")
            time.sleep(15.0)
            sim_state["current_step"] = "at_delivery"
            sim_state["step_index"] = 5
            sim_state["step_title"] = f"Entrega Concluída ({item.upper()})"
            sim_state["step_description"] = "Peça entregue no destino. Clique em 'CONFIRMAR E IR PARA O PRÓXIMO PASSO' para retornar à Estação de Carga."
            sim_state["waiting_confirmation"] = True
            sim_state["busy"] = False

        threading.Thread(target=_step_delivery, daemon=True).start()
        return {"status": "success", "message": f"Navegando para o destino '{target_wp}'..."}

    elif step == "at_delivery":
        # Passo 4 (Final): Retornar à Dock Station
        sim_state["current_step"] = "returning_dock_final"
        sim_state["step_index"] = 6
        sim_state["step_title"] = "Retornando à Estação de Carga (Dock)"
        sim_state["step_description"] = "Navegando para 'predock_point' e executando Docking..."
        sim_state["waiting_confirmation"] = False
        sim_state["busy"] = True

        def _step_dock_final():
            trigger_dock()
            time.sleep(12.0)
            sim_state["current_step"] = "completed"
            sim_state["step_index"] = 7
            sim_state["step_title"] = "Simulação Concluída com Sucesso!"
            sim_state["step_description"] = "O TurtleBot 4 retornou e acoplou com sucesso na Dock Station."
            sim_state["waiting_confirmation"] = False
            sim_state["busy"] = False

        threading.Thread(target=_step_dock_final, daemon=True).start()
        return {"status": "success", "message": "Retornando para a Dock Station..."}

    return {"status": "idle", "message": "Nenhum próximo passo disponível."}

@router.post("/simulation/stop")
def stop_simulation():
    sim_state["active"] = False
    sim_state["current_step"] = "idle"
    sim_state["step_title"] = "Simulação Encerrada"
    sim_state["step_description"] = "Modo simulado desativado."
    sim_state["waiting_confirmation"] = False
    sim_state["busy"] = False
    
    # Retorna robô à dock se estiver em movimento
    trigger_dock()
    return {"status": "success", "message": "Simulação cancelada e robô direcionado à Dock Station."}

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
        if target_file:
            if os.path.exists(target_file):
                with open(target_file, "r") as f:
                    raw = [l.strip() for l in f.readlines() if l.strip()]
                    return {"status": "success", "source": source, "logs": raw[-lines:] if raw else [f"[{source.upper()}] O arquivo {target_file} está vazio."]}
            else:
                return {"status": "success", "source": source, "logs": [f"[{source.upper()}] Nenhum log gerado ainda em {target_file}. Clique no botão correspondente para iniciar!"]}
        
        # Se for "all", consolida de todos os arquivos ou docker
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

_dock_lock = threading.Lock()
_undock_lock = threading.Lock()

@router.post("/dock")
def trigger_dock():
    """Envia o comando de Docking (Ir para Estação de Carga) de forma assíncrona ao TurtleBot 4 com prevenção de acúmulo de processos."""
    if not _dock_lock.acquire(blocking=False):
        return {"status": "busy", "message": "Um comando de Docking já está em processamento. Aguarde a conclusão da manobra."}

    try:
        subprocess.run("pkill -9 -f 'send_goal /dock' 2>/dev/null || true", shell=True, timeout=3)
        def _exec_dock():
            try:
                cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /dock irobot_create_msgs/action/Dock "{{}}"'
                res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=25)
                node = get_turtlebot_node()
                if "SUCCEEDED" in res.stdout or "is_docked: true" in res.stdout:
                    print("[INFO TB4] Docking físico concluído com SUCESSO!")
                    node.clear_dock_override()
                    node.is_docked = True
                else:
                    print(f"[WARN TB4] Docking físico não reportou sucesso: {res.stdout}")
            except Exception as e:
                print(f"[ERROR TB4] Exceção na execução do Docking: {e}")
            finally:
                _dock_lock.release()

        threading.Thread(target=_exec_dock, daemon=True).start()
        return {"status": "success", "message": "Comando de Docking enviado! Aguardando confirmação do robô..."}
    except Exception as e:
        _dock_lock.release()
        raise HTTPException(status_code=500, detail=f"Falha ao acionar Docking: {e}")

@router.post("/undock")
def trigger_undock():
    """Envia o comando de Undocking (Sair da Estação de Carga) ao TurtleBot 4 com validação real e sem acúmulo de processos."""
    if not _undock_lock.acquire(blocking=False):
        return {"status": "busy", "message": "Um comando de Undock já está em processamento. Aguarde a conclusão da manobra."}

    try:
        subprocess.run("pkill -9 -f 'send_goal /undock' 2>/dev/null || true", shell=True, timeout=3)
        def _exec_undock():
            try:
                cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /undock irobot_create_msgs/action/Undock "{{}}"'
                res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=25)
                node = get_turtlebot_node()
                if "SUCCEEDED" in res.stdout or "is_docked: false" in res.stdout:
                    print("[INFO TB4] Undock físico concluído com SUCESSO!")
                    node.force_undock_override(3600.0)
                    node.is_docked = False
                else:
                    print(f"[WARN TB4] Undock físico não reportou sucesso: {res.stdout}")
            except Exception as e:
                print(f"[ERROR TB4] Exceção na execução do Undock: {e}")
            finally:
                _undock_lock.release()

        threading.Thread(target=_exec_undock, daemon=True).start()
        return {"status": "success", "message": "Comando de Undocking enviado! Aguardando confirmação do robô..."}
    except Exception as e:
        _undock_lock.release()
        raise HTTPException(status_code=500, detail=f"Falha ao acionar Undocking: {e}")

class DockStatusPayload(BaseModel):
    is_docked: bool

@router.post("/set_dock_status")
def set_dock_status(payload: DockStatusPayload):
    """Força manualmente o status de docking (True ou False) sobrescrevendo leituras presas da telemetria."""
    try:
        node = get_turtlebot_node()
        node.set_dock_override(payload.is_docked, duration_sec=3600.0)
        state_str = "DOCKED (Na Estação)" if payload.is_docked else "UNDOCKED (Livre / Fora da Estação)"
        return {"status": "success", "is_docked": payload.is_docked, "message": f"Status alterado manualmente para {state_str}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao alterar status de dock: {e}")

@router.post("/launch_localization")
def launch_localization():
    """Lança o módulo de Localização Nav2 com o mapa B002 e bond_timeout=30.0. Limpa processos antigos primeiro."""
    try:
        # Limpa processos antigos de localização para evitar zumbis
        subprocess.run(
            "pkill -9 -f 'localization.launch.py' 2>/dev/null ; "
            "pkill -9 -f 'map_server' 2>/dev/null ; "
            "pkill -9 -f 'amcl' 2>/dev/null ; "
            "pkill -9 -f 'lifecycle_manager_localization' 2>/dev/null ; "
            "sleep 3 || true",
            shell=True, timeout=8
        )
        tb4_ws = get_tb4_workspace()
        map_path = os.path.join(tb4_ws, "maps/B002_map.yaml")
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd = f'cd {tb4_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation localization.launch.py map:={map_path} use_sim_time:=false bond_timeout:=30.0 > /tmp/nav2_localization.log 2>&1'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash", start_new_session=True)
        return {"status": "success", "message": "Localização Nav2 (B002_map.yaml) iniciada com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar Localização: {e}")

@router.post("/launch_nav2")
def launch_nav2():
    """Lança o Stack de Navegação Nav2 com as configurações do projeto. Limpa processos antigos primeiro."""
    try:
        # Limpa processos antigos de navegação para evitar zumbis
        subprocess.run(
            "pkill -9 -f 'nav2.launch.py' 2>/dev/null ; "
            "pkill -9 -f 'controller_server' 2>/dev/null ; "
            "pkill -9 -f 'planner_server' 2>/dev/null ; "
            "pkill -9 -f 'bt_navigator' 2>/dev/null ; "
            "pkill -9 -f 'smoother_server' 2>/dev/null ; "
            "pkill -9 -f 'behavior_server' 2>/dev/null ; "
            "pkill -9 -f 'route_server' 2>/dev/null ; "
            "pkill -9 -f 'waypoint_follower' 2>/dev/null ; "
            "pkill -9 -f 'velocity_smoother' 2>/dev/null ; "
            "pkill -9 -f 'collision_monitor' 2>/dev/null ; "
            "pkill -9 -f 'opennav_docking' 2>/dev/null ; "
            "pkill -9 -f 'lifecycle_manager_navigation' 2>/dev/null ; "
            "sleep 3 || true",
            shell=True, timeout=8
        )
        tb4_ws = get_tb4_workspace()
        params_path = os.path.join(tb4_ws, "config/nav2_custom.yaml")
        subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
        cmd = f'cd {tb4_ws} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation nav2.launch.py params_file:={params_path} use_sim_time:=false bond_timeout:=30.0 > /tmp/nav2_stack.log 2>&1'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash", start_new_session=True)
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
        subprocess.Popen(cmd_viz, shell=True, executable="/bin/bash", start_new_session=True)
        return {"status": "success", "message": "Janela do RViz Nav2 disparada no monitor do PC Host!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao abrir RViz Nav2: {e}")

@router.post("/stop_localization")
def stop_localization():
    """Manda Ctrl+C / encerra o processo de Localização Nav2 (localization.launch.py, map_server, amcl)."""
    try:
        subprocess.run("pkill -9 -f 'localization.launch.py' 2>/dev/null || pkill -9 -f 'map_server' 2>/dev/null || true", shell=True)
        return {"status": "success", "message": "Processo de Localização encerrado (Ctrl+C) com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao parar Localização: {e}")

@router.post("/stop_nav2")
def stop_nav2():
    """Manda Ctrl+C / encerra o Stack de Navegação Nav2 (nav2.launch.py, bt_navigator, planner_server, etc) preservando o mapa."""
    try:
        subprocess.run("pkill -9 -f 'nav2.launch.py' 2>/dev/null || pkill -9 -f 'bt_navigator' 2>/dev/null || pkill -9 -f 'controller_server' 2>/dev/null || pkill -9 -f 'planner_server' 2>/dev/null || pkill -9 -f 'lifecycle_manager_navigation' 2>/dev/null || true", shell=True)
        return {"status": "success", "message": "Stack de Navegação Nav2 encerrado preservando Mapa/Localização!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao parar Nav2: {e}")

@router.post("/stop_viz")
def stop_viz():
    """Manda Ctrl+C / encerra o RViz2 (view_navigation.launch.py, rviz2)."""
    try:
        subprocess.run("pkill -9 -f 'view_navigation.launch.py' 2>/dev/null || pkill -9 -f 'rviz2' 2>/dev/null || true", shell=True)
        return {"status": "success", "message": "Janela do RViz2 encerrada (Ctrl+C) com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao fechar RViz2: {e}")

@router.post("/launch_mission_manager")
def launch_mission_manager():
    """Inicializa o Gerenciador de Missões (mission_manager.py)."""
    try:
        tb4_ws = get_tb4_workspace()
        subprocess.run("pkill -9 -f 'scripts/mission_manager.py' 2>/dev/null || true", shell=True)
        time.sleep(0.3)
        cmd = f'cd {tb4_ws} && {JAZZY_ENV_CMD_DS} && PYTHONUNBUFFERED=1 python3 -u scripts/mission_manager.py --ros-args --params-file params/waypoints.yaml > /tmp/nav2_mission_manager.log 2>&1'
        subprocess.Popen(cmd, shell=True, executable="/bin/bash", start_new_session=True)
        return {"status": "success", "message": "Nó Mestre do Mission Manager inicializado!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar Mission Manager: {e}")

@router.post("/stop_mission_manager_process")
def stop_mission_manager_process():
    """Manda Ctrl+C / encerra o processo do Mission Manager (mission_manager.py) para permitir reiniciar do zero."""
    try:
        subprocess.run("pkill -9 -f 'scripts/mission_manager.py' 2>/dev/null || true", shell=True)
        return {"status": "success", "message": "Processo do Mission Manager finalizado (Ctrl+C) com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao encerrar Mission Manager: {e}")

@router.post("/trigger_delivery")
def trigger_delivery():
    """Aciona o serviço ROS 2 de entrega de peças (/start_delivery)."""
    try:
        node = get_turtlebot_node()
        node.call_trigger_service("start_delivery")
        return {"status": "success", "message": "Rotina de Entrega (/start_delivery) acionada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar rotina de entrega: {e}")

@router.post("/trigger_failure")
def trigger_failure():
    """Aciona o serviço ROS 2 de recolhimento de peça com defeito / descarte (/start_failure)."""
    try:
        node = get_turtlebot_node()
        node.call_trigger_service("start_failure")
        return {"status": "success", "message": "Rotina de Falha/Descarte (/start_failure) acionada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar rotina de falha: {e}")

@router.post("/trigger_restock")
def trigger_restock():
    """Aciona o serviço ROS 2 de reabastecimento de matéria-prima (/start_restock)."""
    try:
        node = get_turtlebot_node()
        node.call_trigger_service("start_restock")
        return {"status": "success", "message": "Rotina de Reabastecimento (/start_restock) acionada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar rotina de reabastecimento: {e}")

@router.post("/trigger_patrol")
def trigger_patrol():
    """Aciona o serviço ROS 2 de ronda/patrulha (/start_patrol)."""
    try:
        node = get_turtlebot_node()
        node.call_trigger_service("start_patrol")
        return {"status": "success", "message": "Rotina de Patrulha (/start_patrol) acionada!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao acionar rotina de patrulha: {e}")

@router.post("/stop_mission")
def stop_mission():
    """Interrompe e cancela qualquer missão ativa no Mission Manager e força parada dos motores."""
    try:
        node = get_turtlebot_node()
        node.call_trigger_service("stop_mission")
        node.send_cmd_vel(0.0, 0.0)
        return {"status": "success", "message": "🛑 Missão interrompida! Robô parado e Mission Manager desocupado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao interromper missão: {e}")

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

@router.post("/restart_daemon")
def restart_daemon():
    """Reinicia o daemon do ROS 2 (ros2 daemon stop && ros2 daemon start) com o ambiente do TurtleBot 4."""
    try:
        cmd = f'{JAZZY_ENV_CMD} && ros2 daemon stop && ros2 daemon start'
        res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=10)
        return {
            "status": "success",
            "message": "Daemon do ROS 2 reiniciado com sucesso!",
            "output": res.stdout.strip()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao reiniciar daemon ROS 2: {e}")

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
