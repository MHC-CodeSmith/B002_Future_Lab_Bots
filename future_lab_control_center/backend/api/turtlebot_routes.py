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

_EXPECTED_ROS_ENV = {
    "ROS_DOMAIN_ID": "0",
    "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
    "ROS_SUPER_CLIENT": "True",
    "ROS_AUTOMATIC_DISCOVERY_RANGE": "SUBNET",
}

def _container_env() -> dict:
    """Ambiente com que o processo foi iniciado (compose/Dockerfile), sem as
    sobrescritas feitas em runtime por main.py e turtlebot_node.py."""
    try:
        with open("/proc/self/environ", "rb") as f:
            raw = f.read().decode("utf-8", "replace")
        return dict(i.split("=", 1) for i in raw.split("\0") if "=" in i)
    except Exception:
        return dict(os.environ)

def _assert_ros_env():
    env = _container_env()
    for k, esperado in _EXPECTED_ROS_ENV.items():
        atual = env.get(k)
        if atual != esperado:
            print(f"[ENV WARN] {k}={atual!r} no ambiente do container, esperado {esperado!r} "
                  f"— o backend corrige em runtime, mas a origem divergiu")
    if env.get("FASTDDS_BUILTIN_TRANSPORTS"):
        print("[ENV WARN] FASTDDS_BUILTIN_TRANSPORTS definido no ambiente do container "
              "— vaza para os subprocessos e derruba o Discovery Server")

_assert_ros_env()

JAZZY_ENV_CMD = (
    "source /home/future-lab/B002_Future_Lab_Bots/turtlebot4_jazzy/setup.bash && "
    "export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET && "
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
    item: str = "blue"  # "blue", "red", "invalid", "restock"

@router.get("/ros_env")
def get_ros_env():
    """Reporta o ambiente ROS efetivo do processo e o que o nó rclpy enxerga."""
    from rclpy.utilities import get_rmw_implementation_identifier
    node = get_turtlebot_node()
    topics = node.get_topic_names_and_types()
    bat_pubs = node.get_publishers_info_by_topic("/battery_state")
    dock_pubs = node.get_publishers_info_by_topic("/dock_status")
    return {
        "rmw": get_rmw_implementation_identifier(),
        "domain_id": os.environ.get("ROS_DOMAIN_ID"),
        "discovery_server": os.environ.get("ROS_DISCOVERY_SERVER"),
        "super_client": os.environ.get("ROS_SUPER_CLIENT"),
        "auto_discovery_range": os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE"),
        "fastdds_builtin_transports": os.environ.get("FASTDDS_BUILTIN_TRANSPORTS"),
        "topics_visible": len(topics),
        "sees_battery": any(t[0] == "/battery_state" for t in topics),
        "sees_dock_status": any(t[0] == "/dock_status" for t in topics),
        "battery_pub_qos": [str(p.qos_profile.reliability) for p in bat_pubs],
        "dock_pub_qos": [str(p.qos_profile.reliability) for p in dock_pubs],
    }

_PROCESS_PATTERNS = {
    "localization": "localization.launch.py",
    "nav2": "nav2.launch.py",
    "viz": "view_navigation.launch.py",
    "mission_manager": "scripts/mission_manager.py",
}

_processes_cache = {"timestamp": 0.0, "data": {}}

@router.get("/processes")
def get_processes():
    """Estado dos processos da stack de navegação iniciados pelo backend."""
    now = time.time()
    if (now - _processes_cache["timestamp"]) < 3.0:
        return _processes_cache["data"]

    node = get_turtlebot_node()
    services = set()
    try:
        services = {s[0] for s in node.get_service_names_and_types()}
    except Exception:
        pass

    out = {}
    for nome, padrao in _PROCESS_PATTERNS.items():
        try:
            res = subprocess.run(["pgrep", "-f", padrao],
                                 capture_output=True, text=True, timeout=2)
            pids = [p for p in res.stdout.split() if p.strip()]
            item = {
                "launched_by_dashboard": bool(pids),
                "pids": pids,
                "pattern": padrao
            }
            if nome == "mission_manager":
                item["visible_on_ros_graph"] = "/start_delivery" in services
            out[nome] = item
        except Exception as e:
            out[nome] = {"launched_by_dashboard": None, "pids": [], "pattern": padrao, "error": str(e)}

    _processes_cache["timestamp"] = now
    _processes_cache["data"] = out
    return out

def _nav_hint(faltando: list, checks: dict = None) -> str:
    if not faltando:
        if checks and checks.get("undocked") is False:
            return ("Stack pronta, mas o robô está acoplado. Faça Undock (Passo 3) "
                    "antes de enviar metas diretas ao Nav2 — a Create 3 ignora "
                    "/cmd_vel na dock e o costmap nasce com a estrutura da dock "
                    "dentro da footprint. As rotinas de missão fazem o undock sozinhas.")
        return "Stack de navegação pronta."
    if "map" in faltando or "amcl_pose" in faltando:
        return "Localização não está no ar. Use '1. Iniciar Localização', abra o RViz (Passo 2), faça Undock (Passo 3) e defina a pose inicial (Passo 4)."
    if "navigate_to_pose" in faltando or "global_costmap" in faltando:
        return "Nav2 não está no ar. Use '5. Lançar Nav2 Stack'."
    if "start_delivery" in faltando or "stop_mission" in faltando:
        return "Mission Manager não está no ar. Use 'Iniciar Mission Manager'."
    if "create3_alive" in faltando or "odom" in faltando or "scan" in faltando:
        return "Sensores da base não estão publicando. Verifique o TurtleBot 4 e o Discovery Server."
    return "Verifique os itens em 'missing'."

_nav_readiness_cache = {"timestamp": 0.0, "data": None}

@router.get("/nav_readiness")
def get_nav_readiness():
    """Prontidão da navegação, verificada por introspecção ROS. Somente leitura."""
    now = time.time()
    if _nav_readiness_cache["data"] is not None and (now - _nav_readiness_cache["timestamp"]) < 3.0:
        return _nav_readiness_cache["data"]

    from rclpy.action import get_action_names_and_types
    node = get_turtlebot_node()

    create3_alive = node.telemetry_fresh()

    topics = {t[0] for t in node.get_topic_names_and_types()}
    services = {s[0] for s in node.get_service_names_and_types()}
    try:
        actions = {a[0] for a in get_action_names_and_types(node=node)}
    except Exception:
        actions = set()

    checks = {
        # Base física (Create 3)
        "create3_alive":         create3_alive,
        "create3_dock_action":   ("/dock" in actions) if create3_alive else None,
        "create3_undock_action": ("/undock" in actions) if create3_alive else None,
        "undocked":              (not node.is_docked) if create3_alive else None,
        "odom":                  ("/odom" in topics) if create3_alive else None,
        "scan":                  ("/scan" in topics) if create3_alive else None,
        # Localização
        "map":                   node.count_publishers("/map") > 0,
        "amcl_pose":             node.count_publishers("/amcl_pose") > 0,
        "amcl_converged":        node.get_amcl()["converged"],
        # Navegação
        "navigate_to_pose":      "/navigate_to_pose" in actions,
        "global_costmap":        node.count_publishers("/global_costmap/costmap") > 0,
        # Missões
        "start_delivery":        "/start_delivery" in services,
        "start_failure":         "/start_failure" in services,
        "start_restock":         "/start_restock" in services,
        "stop_mission":          "/stop_mission" in services,
    }

    obrigatorios = ["create3_alive", "odom", "scan", "map", "amcl_pose",
                    "navigate_to_pose", "global_costmap", "create3_undock_action",
                    "start_delivery", "stop_mission"]
    faltando = [k for k in obrigatorios if not checks.get(k)]

    out = {
        "ready": not faltando,
        "missing": faltando,
        "checks": checks,
        "hint": _nav_hint(faltando, checks),
    }
    _nav_readiness_cache["timestamp"] = now
    _nav_readiness_cache["data"] = out
    return out

@router.get("/amcl_status")
def get_amcl_status():
    """Pose e covariância do AMCL. Somente leitura."""
    return get_turtlebot_node().get_amcl()

@router.post("/clear_costmaps")
def clear_costmaps():
    """Limpa os costmaps global e local do Nav2. Caminho de recuperação —
    sem guarda de telemetria, igual ao /dock."""
    servicos = [
        "/global_costmap/clear_entirely_global_costmap",
        "/local_costmap/clear_entirely_local_costmap",
    ]
    resultados = {}
    for srv in servicos:
        try:
            cmd = f'{JAZZY_ENV_CMD} && ros2 service call {srv} nav2_msgs/srv/ClearEntireCostmap "{{}}"'
            res = subprocess.run(cmd, shell=True, executable="/bin/bash",
                                 capture_output=True, text=True, timeout=10)
            saida = (res.stdout or "") + (res.stderr or "")
            resultados[srv] = ("response" in saida and res.returncode == 0)
        except subprocess.TimeoutExpired:
            resultados[srv] = False
        except Exception:
            resultados[srv] = False

    algum_ok = any(resultados.values())
    if not algum_ok:
        raise HTTPException(
            status_code=503,
            detail="Nenhum costmap respondeu. O Nav2 está no ar? "
                   "Confira '5. Lançar Nav2 Stack'."
        )
    return {"status": "success", "servicos": resultados,
            "message": "Costmaps limpos. Reenvie a meta."}

@router.get("/nav_poses")
def get_nav_poses():
    """Retorna as poses configuradas em nav_poses.yaml."""
    try:
        import yaml
        nav_poses_file = "/app/backend/config/nav_poses.yaml"
        if not os.path.exists(nav_poses_file):
            nav_poses_file = os.path.join(os.path.dirname(__file__), "../config/nav_poses.yaml")
        if os.path.exists(nav_poses_file):
            with open(nav_poses_file, "r") as f:
                data = yaml.safe_load(f)
                return data or {"dock_pose": None}
        return {"dock_pose": None}
    except Exception as e:
        return {"dock_pose": None, "error": str(e)}

@router.post("/save_dock_pose")
def save_dock_pose():
    """Grava a pose atual do AMCL como pose da dock em nav_poses.yaml. Exige convergência e robô docado."""
    from datetime import datetime
    import yaml
    node = get_turtlebot_node()
    a = node.get_amcl()
    if not a["amcl_ok"]:
        raise HTTPException(
            status_code=409,
            detail="AMCL não está publicando. Inicie a Localização primeiro."
        )
    if not a["converged"]:
        raise HTTPException(
            status_code=409,
            detail=f"AMCL ainda não convergiu (covariância {a['covariance']}). "
                   f"Gire o robô alguns graus e tente de novo."
        )
    if not node.is_docked:
        raise HTTPException(
            status_code=409,
            detail="O robô precisa estar acoplado na dock para gravar a dock_pose."
        )

    nav_poses_file = "/app/backend/config/nav_poses.yaml"
    if not os.path.exists(os.path.dirname(nav_poses_file)):
        nav_poses_file = os.path.join(os.path.dirname(__file__), "../config/nav_poses.yaml")

    dock_data = {
        "dock_pose": {
            "x": a["pose"]["x"],
            "y": a["pose"]["y"],
            "yaw": a["pose"]["yaw"],
            "measured": True,
            "measured_at": datetime.now().isoformat(),
            "covariance": a["covariance"],
        }
    }

    HEADER = (
        "# Pose do TurtleBot 4 quando acoplado na dock, no frame \"map\" do B002_map.yaml.\n"
        "# Gravado por POST /api/v1/turtlebot/save_dock_pose com o AMCL convergido.\n"
        "# NAO editar a mao.\n"
    )
    try:
        os.makedirs(os.path.dirname(nav_poses_file), exist_ok=True)
        with open(nav_poses_file, "w") as f:
            f.write(HEADER)
            yaml.dump(dock_data, f, default_flow_style=False, allow_unicode=True)
        return {
            "status": "success",
            "message": f"Pose real da dock gravada com sucesso em {nav_poses_file}!",
            "dock_pose": dock_data["dock_pose"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar nav_poses.yaml: {e}")

def _require_live_telemetry():
    node = get_turtlebot_node()
    if not node.telemetry_fresh():
        raise HTTPException(
            status_code=409,
            detail="Sem telemetria da base há mais de 5 s. Comando de movimento bloqueado — "
                   "verifique a Create 3 antes de operar o robô."
        )

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

_ping_cache = {"timestamp": 0.0, "ok": False}

def _ping_cached(ip: str) -> bool:
    now = time.time()
    if (now - _ping_cache["timestamp"]) < 5.0:
        return _ping_cache["ok"]
    _ping_cache["ok"] = ping_host(ip, timeout_sec=1)
    _ping_cache["timestamp"] = now
    return _ping_cache["ok"]

@router.get("/status")
def get_turtlebot_status():
    """Retorna o status do TurtleBot 4 (bateria, posição, docking e modo simulado)."""
    tb_ip = "192.168.0.129"
    ping_ok = _ping_cached(tb_ip)
    node = get_turtlebot_node()

    if not ping_ok:
        return {
            "status": "offline",
            "ping_ok": False,
            "telemetry_ok": False,
            "telemetry_age_s": None,
            "battery_percentage": None,
            "battery_current": None,
            "charging": None,
            "is_docked": None,
            "current_pose": None,
            "oakd_streaming": False,
            "sim_state": sim_state,
        }

    st = node.get_status()
    st["ping_ok"] = True
    st["sim_state"] = sim_state
    return st

@router.post("/simulation/start")
def start_simulation(payload: SimulationStartSchema):
    _require_live_telemetry()
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
            try:
                trigger_dock()
                time.sleep(8.0)
                sim_state["current_step"] = "at_dock"
                sim_state["step_index"] = 2
                sim_state["step_title"] = "Robô na Estação de Carga (Pronto)"
                sim_state["step_description"] = f"Robô acoplado na dock. Peça selecionada: {payload.item.upper()}. Clique em 'CONFIRMAR E IR PARA O PRÓXIMO PASSO' para iniciar o Undock."
                sim_state["waiting_confirmation"] = True
            except Exception as e:
                sim_state["step_title"] = "Falha na Simulação (Pré-requisito)"
                sim_state["step_description"] = f"Erro no Docking de pré-requisito: {e}"
            finally:
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
    _require_live_telemetry()
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
            try:
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
            except Exception as e:
                sim_state["step_title"] = "Falha no Undock / Coleta"
                sim_state["step_description"] = f"Erro no passo de coleta: {e}"
            finally:
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
            try:
                cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{{pose: {{header: {{frame_id: map}}, pose: {{position: {{x: {target_x}, y: {target_y}, z: 0.0}}, orientation: {{w: 1.0}}}}}}}}"'
                subprocess.Popen(cmd, shell=True, executable="/bin/bash")
                time.sleep(15.0)
                sim_state["current_step"] = "at_delivery"
                sim_state["step_index"] = 5
                sim_state["step_title"] = f"Entrega Concluída ({item.upper()})"
                sim_state["step_description"] = "Peça entregue no destino. Clique em 'CONFIRMAR E IR PARA O PRÓXIMO PASSO' para retornar à Estação de Carga."
                sim_state["waiting_confirmation"] = True
            except Exception as e:
                sim_state["step_title"] = "Falha na Entrega"
                sim_state["step_description"] = f"Erro no passo de entrega: {e}"
            finally:
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
            try:
                trigger_dock()
                time.sleep(12.0)
                sim_state["current_step"] = "completed"
                sim_state["step_index"] = 7
                sim_state["step_title"] = "Simulação Concluída com Sucesso!"
                sim_state["step_description"] = "O TurtleBot 4 retornou e acoplou com sucesso na Dock Station."
                sim_state["waiting_confirmation"] = False
            except Exception as e:
                sim_state["step_title"] = "Falha no Docking Final"
                sim_state["step_description"] = f"Erro ao acoplar na dock: {e}"
            finally:
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
    try:
        trigger_dock()
    except Exception as e:
        print(f"[WARN TB4] Erro ao disparar trigger_dock em stop_simulation: {e}")
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
    _require_live_telemetry()
    try:
        node = get_turtlebot_node()
        node.send_cmd_vel(payload.linear_x, payload.angular_z)
        return {"status": "success", "linear_x": payload.linear_x, "angular_z": payload.angular_z}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao enviar teleop: {e}")

class InitialPosePayload(BaseModel):
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0

@router.post("/set_initial_pose")
def set_initial_pose(payload: InitialPosePayload):
    """Define a pose inicial do TurtleBot 4 no mapa (/initialpose) para convergência do AMCL."""
    _require_live_telemetry()
    node = get_turtlebot_node()
    ok, msg = node.publish_initial_pose(payload.x, payload.y, payload.yaw)
    if not ok:
        raise HTTPException(status_code=503, detail=msg)
    return {"status": "success", "message": msg}

_dock_lock = threading.Lock()
_undock_lock = threading.Lock()

@router.post("/dock")
def trigger_dock():
    """Envia o comando de Docking ao TurtleBot 4 e aguarda a confirmação real da manobra.
    
    Sem guarda de telemetria por decisão de projeto: dock é o caminho de recuperação
    quando a base parou de publicar. Não adicionar _require_live_telemetry() aqui.
    """
    if not _dock_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Um comando de Docking já está em processamento no robô. Aguarde a manobra finalizar."
        )

    try:
        node = get_turtlebot_node()
        print("[INFO TB4] Disparando ação /dock no TurtleBot 4...")
        cmd_action = f'{JAZZY_ENV_CMD} && ros2 action send_goal /dock irobot_create_msgs/action/Dock "{{}}"'
        res = subprocess.run(cmd_action, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)

        full_output = res.stdout.strip()
        print(f"[INFO TB4] Resultado do Docking: {full_output}")

        if "SUCCEEDED" in full_output or "is_docked: true" in full_output:
            return {"status": "success", "message": "Docking físico concluído com SUCESSO no TurtleBot 4!"}
        else:
            raise HTTPException(status_code=500, detail=f"Ação /dock não reportou sucesso: {full_output}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Tempo limite esgotado (30s) aguardando o servidor de ação /dock no robô.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar Docking: {e}")
    finally:
        _dock_lock.release()

@router.post("/undock")
def trigger_undock():
    """Envia o comando de Undocking ao TurtleBot 4 e aguarda a confirmação real da manobra."""
    _require_live_telemetry()
    if not _undock_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Um comando de Undock já está em processamento no robô. Aguarde a manobra finalizar."
        )

    try:
        node = get_turtlebot_node()
        print("[INFO TB4] Disparando ação /undock no TurtleBot 4...")
        cmd_action = f'{JAZZY_ENV_CMD} && ros2 action send_goal /undock irobot_create_msgs/action/Undock "{{}}"'
        res = subprocess.run(cmd_action, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=25)

        full_output = res.stdout.strip()
        print(f"[INFO TB4] Resultado do Undock: {full_output}")

        if "SUCCEEDED" in full_output or "is_docked: false" in full_output:
            return {"status": "success", "message": "Undock físico concluído com SUCESSO no TurtleBot 4!"}
        else:
            raise HTTPException(status_code=500, detail=f"Ação /undock não reportou sucesso: {full_output}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Tempo limite esgotado (25s) aguardando o servidor de ação /undock no robô.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar Undock: {e}")
    finally:
        _undock_lock.release()

class DockStatusPayload(BaseModel):
    is_docked: bool

@router.post("/set_dock_status")
def set_dock_status(payload: DockStatusPayload):
    """Obsoleto: O estado de dock vem da telemetria da Create 3 e não pode ser forçado."""
    raise HTTPException(
        status_code=410,
        detail="O estado de dock vem da telemetria da Create 3 e não pode ser forçado."
    )

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
    _require_live_telemetry()
    node = get_turtlebot_node()
    ok, msg = node.call_trigger_service("start_delivery")
    if not ok:
        raise HTTPException(status_code=503, detail=msg)
    return {"status": "success", "message": msg or "Rotina de Entrega acionada!"}

@router.post("/trigger_failure")
def trigger_failure():
    """Aciona o serviço ROS 2 de recolhimento de peça com defeito / descarte (/start_failure)."""
    _require_live_telemetry()
    node = get_turtlebot_node()
    ok, msg = node.call_trigger_service("start_failure")
    if not ok:
        raise HTTPException(status_code=503, detail=msg)
    return {"status": "success", "message": msg or "Rotina de Falha/Descarte acionada!"}

@router.post("/trigger_restock")
def trigger_restock():
    """Aciona o serviço ROS 2 de reabastecimento de matéria-prima (/start_restock)."""
    _require_live_telemetry()
    node = get_turtlebot_node()
    ok, msg = node.call_trigger_service("start_restock")
    if not ok:
        raise HTTPException(status_code=503, detail=msg)
    return {"status": "success", "message": msg or "Rotina de Reabastecimento acionada!"}

@router.post("/trigger_patrol")
def trigger_patrol():
    raise HTTPException(
        status_code=501,
        detail="Rotina de patrulha não implementada: o mission_manager não expõe /start_patrol."
    )

@router.post("/stop_mission")
def stop_mission():
    """Interrompe a missão ativa e força parada dos motores. Nunca falha."""
    node = get_turtlebot_node()
    ok, msg = node.call_trigger_service("stop_mission")
    node.send_cmd_vel(0.0, 0.0)
    return {
        "status": "success",
        "service_ok": ok,
        "message": "🛑 Motores parados." + ("" if ok else f" Aviso: {msg}")
    }

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
        node = get_turtlebot_node()
        cmd = f'ssh -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=no ubuntu@192.168.0.129 "source /etc/turtlebot4/setup.bash && ros2 service call /oakd/start_camera std_srvs/srv/Trigger {{}}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        if res.returncode != 0 and "success=True" not in res.stdout:
            # Tenta via container se o SSH falhou
            cmd_container = f'{JAZZY_ENV_CMD} && ros2 service call /oakd/start_camera std_srvs/srv/Trigger {{}}'
            res = subprocess.run(cmd_container, shell=True, executable="/bin/bash", capture_output=True, text=True, timeout=10)

        out_text = (res.stdout or "") + (res.stderr or "")
        if res.returncode != 0 and "success=True" not in out_text:
            raise HTTPException(status_code=503, detail=f"Serviço /oakd/start_camera falhou ou indisponível: {out_text.strip()[:200]}")

        # Aguarda até 5s para confirmar recepção de frames
        t0 = time.time()
        while time.time() - t0 < 5.0:
            if (time.time() - node.last_frame_time) < 3.0:
                break
            time.sleep(0.3)

        return {
            "status": "success",
            "message": "Câmera OAK-D-PRO despertada com sucesso!",
            "oakd_streaming": (time.time() - node.last_frame_time) < 3.0,
            "stream_url": "/api/v1/turtlebot/oakd_stream"
        }
    except HTTPException:
        raise
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
    """Streaming MJPEG ao vivo da Câmera OAK-D-PRO do TurtleBot 4 com timeout de 5s e limite de 300s por conexão."""
    node = get_turtlebot_node()

    def generate_frames():
        start_wait = time.time()
        t_start = time.time()
        while True:
            if time.time() - t_start > 300.0:
                break
            frame = node.latest_jpeg_frame
            last_frame = getattr(node, 'last_frame_time', 0.0)
            if frame and (time.time() - last_frame < 3.0):
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                time.sleep(0.04)  # ~25 FPS
            else:
                if time.time() - start_wait > 5.0 or (frame and time.time() - last_frame >= 3.0):
                    try:
                        import cv2, numpy as np
                        img = np.zeros((240, 320, 3), dtype=np.uint8)
                        cv2.putText(img, "CAMERA SEM SINAL", (30, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                        _, jpeg = cv2.imencode('.jpg', img)
                        placeholder = jpeg.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + placeholder + b'\r\n')
                    except Exception:
                        pass
                    break
                time.sleep(0.1)

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
