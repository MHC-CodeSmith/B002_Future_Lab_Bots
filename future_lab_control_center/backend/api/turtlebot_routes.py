# ============================================================
# turtlebot_routes.py — API Router do TurtleBot 4 (AMR & Jazzy Stack)
# ============================================================
import os
import time
import math
import subprocess
import threading
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.mission_readiness import mission_readiness
from backend.ros2_nodes.turtlebot_node import get_turtlebot_node
from backend.api.health_routes import _launch_gui_in_pty

router = APIRouter(prefix="/api/v1/turtlebot", tags=["TurtleBot 4"])

_EXPECTED_ROS_ENV = {
    "ROS_DOMAIN_ID": "0",
    "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
    "ROS_SUPER_CLIENT": "True",
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

os.environ["ROS_DOMAIN_ID"] = "0"
os.environ["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
os.environ.pop("ROS_AUTOMATIC_DISCOVERY_RANGE", None)
os.environ["ROS_SUPER_CLIENT"] = "True"
os.environ["ROS_DISCOVERY_SERVER"] = "192.168.0.129:11811;"

JAZZY_ENV_CMD = (
    "source /opt/ros/jazzy/setup.bash && "
    "source /home/future-lab/B002_Future_Lab_Bots/turtlebot4_jazzy/setup.bash && "
    "unset ROS_AUTOMATIC_DISCOVERY_RANGE && "
    "export ROS_SUPER_CLIENT=True && "
    "export ROS_DISCOVERY_SERVER='192.168.0.129:11811;' && "
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


class MissionTestClassSchema(BaseModel):
    """Classe sintética usada somente para testar o handshake do TurtleBot."""

    item: str


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
    """Estado dos processos da stack de navegação consultados via Agente do Host."""
    now = time.time()
    if (now - _processes_cache["timestamp"]) < 2.0:
        return _processes_cache["data"]

    try:
        host_status = _call_host_agent("/status", method="GET", timeout=3.0)
        node = get_turtlebot_node()
        services = set()
        try:
            services = {s[0] for s in node.get_service_names_and_types()}
        except Exception:
            pass

        out = {}
        for nome, padrao in _PROCESS_PATTERNS.items():
            raw = host_status.get(nome, {})
            # Compatibilidade temporaria com um agente antigo, que devolvia bool.
            if isinstance(raw, bool):
                raw = {
                    "running": raw,
                    "owned": raw,
                    "instances": 1 if raw else 0,
                    "pids": ["host_active"] if raw else [],
                    "error": None,
                }
            is_active = bool(raw.get("running"))
            item = {
                "running": is_active,
                "launched_by_dashboard": bool(raw.get("owned")),
                "instances": int(raw.get("instances", 0)),
                "pid": raw.get("pid"),
                "pgid": raw.get("pgid"),
                "pids": raw.get("pids", []),
                "pattern": padrao,
                "error": raw.get("error"),
            }
            if nome == "mission_manager":
                item["visible_on_ros_graph"] = "/start_delivery" in services
            out[nome] = item
        _processes_cache["timestamp"] = now
        _processes_cache["data"] = out
        return out
    except Exception as e:
        out = {}
        for nome, padrao in _PROCESS_PATTERNS.items():
            out[nome] = {"launched_by_dashboard": False, "pids": [], "pattern": padrao, "error": str(e)}
        return out

def _nav_hint(faltando: list, checks: dict = None) -> str:
    if "scan" in faltando and checks and checks.get("undocked") is False:
        return ("O TurtleBot está acoplado e o modo de economia desligou o motor do RPLidar. "
                "O LaserScan só ficará disponível depois de um undock autorizado ou de o "
                "operador ligar explicitamente o motor do lidar.")
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
        if checks and checks.get("undocked") is False:
            return ("Nav2 não pode ser iniciado a frio enquanto o TurtleBot está dockado: "
                    "a Create 3 suspende odom→base_link. Faça um Undock autorizado, aguarde "
                    "scan/odom/TF e então use 'Lançar Nav2 Stack'.")
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
    scan_status = node.get_scan_status()
    amcl_status = node.get_amcl()

    try:
        host_status = _call_host_agent("/status", method="GET", timeout=2.0)
    except Exception:
        host_status = {}

    localization_process = host_status.get("localization", {})
    nav2_process = host_status.get("nav2", {})
    localization_running = bool(
        isinstance(localization_process, dict)
        and localization_process.get("running")
        and localization_process.get("instances") == 1
    )
    nav2_running = bool(
        isinstance(nav2_process, dict)
        and nav2_process.get("running")
        and nav2_process.get("instances") == 1
    )

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
        "scan":                  scan_status["fresh"] if create3_alive else None,
        # Localização
        "map":                   localization_running and node.count_publishers("/map") > 0,
        "amcl_pose":             localization_running and amcl_status.get("amcl_ok", False),
        "amcl_converged":        localization_running and amcl_status["converged"],
        # Navegação
        "navigate_to_pose":      nav2_running and "/navigate_to_pose" in actions,
        "global_costmap":        nav2_running and node.count_publishers("/global_costmap/costmap") > 0,
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
    mission = mission_readiness(checks)

    out = {
        "ready": not faltando,
        "missing": faltando,
        "mission_ready": mission["ready"],
        "mission_missing": mission["missing"],
        "mission_required": mission["required"],
        "mission_start_mode": mission["start_mode"],
        "mission_hint": mission["hint"],
        "checks": checks,
        "evidence": {
            "scan": scan_status,
            "localization_process": localization_process,
            "nav2_process": nav2_process,
            "amcl": amcl_status,
        },
        "hint": _nav_hint(faltando, checks),
    }
    _nav_readiness_cache["timestamp"] = now
    _nav_readiness_cache["data"] = out
    return out


def _require_mission_ready() -> dict:
    """Impõe no backend a mesma guarda exibida pelo dashboard."""
    readiness = get_nav_readiness()
    if readiness.get("mission_ready") is not True:
        missing = readiness.get("mission_missing") or ["estado de missão desconhecido"]
        raise HTTPException(
            status_code=409,
            detail=(
                "Missão recusada porque a prontidão medida não passou: "
                + ", ".join(str(item) for item in missing)
            ),
        )
    return readiness

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
    """Retorna a dock_pose de nav_poses.yaml e os waypoints reais de waypoints.yaml."""
    try:
        import yaml
        nav_poses_file = "/app/backend/config/nav_poses.yaml"
        if not os.path.exists(nav_poses_file):
            nav_poses_file = os.path.join(os.path.dirname(__file__), "../config/nav_poses.yaml")
        out = {"dock_pose": None}
        if os.path.exists(nav_poses_file):
            with open(nav_poses_file, "r") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    out.update(data)
        
        # Acrescenta waypoints do waypoints.yaml
        try:
            wp_params = _waypoints()
            for key, val in wp_params.items():
                if isinstance(val, (list, tuple)) and len(val) >= 3:
                    out[key] = [float(val[0]), float(val[1]), float(val[2])]
        except Exception as wp_err:
            out["waypoints_error"] = str(wp_err)

        return out
    except Exception as e:
        return {"dock_pose": None, "error": str(e)}

@router.post("/save_dock_pose")
def save_dock_pose():
    """Grava a pose atual do AMCL como pose da dock em nav_poses.yaml. Exige amcl_ok, robô docado e limiares de dock."""
    from datetime import datetime
    import yaml
    node = get_turtlebot_node()
    a = node.get_amcl()
    if not a["amcl_ok"]:
        motivo = a.get("motivo") or "AMCL não está publicando"
        raise HTTPException(
            status_code=409,
            detail=f"AMCL indisponível ({motivo}). Inicie a Localização primeiro."
        )

    COV_XY_MAX_DOCK = 0.09
    COV_YAW_MAX_DOCK = 0.12

    c = a.get("covariance") or {}
    cov_x = c.get("x", 1.0)
    cov_y = c.get("y", 1.0)
    cov_yaw = c.get("yaw", 1.0)

    dock_converged = (cov_x < COV_XY_MAX_DOCK and cov_y < COV_XY_MAX_DOCK and cov_yaw < COV_YAW_MAX_DOCK)
    if not dock_converged:
        raise HTTPException(
            status_code=409,
            detail=f"AMCL ainda não convergiu para o estado docado (covariância {c}). "
                   f"Limiares exigidos em dock: xy < {COV_XY_MAX_DOCK}, yaw < {COV_YAW_MAX_DOCK}."
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
    "busy": False,
    "last_nav_result": None
}

_simulation_popens = []
_simulation_popens_lock = threading.Lock()

def _register_sim_popen(proc: subprocess.Popen):
    with _simulation_popens_lock:
        _simulation_popens.append(proc)

def _kill_sim_popens() -> int:
    killed_count = 0
    with _simulation_popens_lock:
        while _simulation_popens:
            p = _simulation_popens.pop()
            try:
                if p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=1.0)
                    except Exception:
                        p.kill()
                    killed_count += 1
            except Exception:
                try:
                    p.kill()
                    killed_count += 1
                except Exception:
                    pass
    return killed_count

_WAYPOINTS_CACHE = {"timestamp": 0.0, "data": None}

def _waypoints() -> dict:
    """Lê turtlebot4_jazzy/params/waypoints.yaml. Somente leitura, cache de 30 s."""
    now = time.time()
    if _WAYPOINTS_CACHE["data"] is not None and (now - _WAYPOINTS_CACHE["timestamp"]) < 30.0:
        return _WAYPOINTS_CACHE["data"]

    wp_file = os.path.join(get_tb4_workspace(), "params", "waypoints.yaml")

    if not os.path.exists(wp_file):
        raise HTTPException(
            status_code=503,
            detail=f"Arquivo de waypoints {wp_file} não encontrado."
        )

    try:
        import yaml
        with open(wp_file, "r") as f:
            raw = yaml.safe_load(f)
        
        params = raw.get("/**", {}).get("ros__parameters", {})
        _WAYPOINTS_CACHE["timestamp"] = now
        _WAYPOINTS_CACHE["data"] = params
        return params
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Erro ao ler waypoints de {wp_file}: {e}"
        )

def _get_waypoint_pose(name: str) -> tuple:
    """Obtém (x, y, yaw) do waypoint lido de waypoints.yaml. Lança HTTP 503 se a chave não existir."""
    params = _waypoints()
    if name not in params:
        raise HTTPException(
            status_code=503,
            detail=f"Waypoint '{name}' não configurado em waypoints.yaml."
        )
    val = params[name]
    if not isinstance(val, (list, tuple)) or len(val) < 3:
        raise HTTPException(
            status_code=503,
            detail=f"Waypoint '{name}' em waypoints.yaml inválido (esperado [x, y, yaw])."
        )
    return float(val[0]), float(val[1]), float(val[2])

def _yaw_to_quaternion(yaw: float) -> tuple:
    half_yaw = yaw * 0.5
    return math.sin(half_yaw), math.cos(half_yaw)

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
        px, py, pyaw = _get_waypoint_pose("pickup_point")
        pz, pw = _yaw_to_quaternion(pyaw)

        sim_state["current_step"] = "going_pickup"
        sim_state["step_index"] = 2
        sim_state["step_title"] = "Undock & Indo para Ponto de Coleta"
        sim_state["step_description"] = f"Desengatando da dock e navegando até 'pickup_point' ({px}, {py})..."
        sim_state["waiting_confirmation"] = False
        sim_state["busy"] = True

        def _step_pickup():
            try:
                trigger_undock()
                time.sleep(3.0)
                cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{{pose: {{header: {{frame_id: map}}, pose: {{position: {{x: {px}, y: {py}, z: 0.0}}, orientation: {{z: {pz}, w: {pw}}}}}}}}}"'
                proc = subprocess.Popen(cmd, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                _register_sim_popen(proc)
                try:
                    stdout, _ = proc.communicate(timeout=90.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout = "Timeout (90s) aguardando chegada ao pickup_point."
                
                output = stdout or ""
                is_succeeded = ("STATUS_SUCCEEDED" in output or "Goal finished with status SUCCEEDED" in output or "SUCCEEDED" in output) and proc.returncode == 0
                sim_state["last_nav_result"] = "SUCCEEDED" if is_succeeded else "FAILED"

                if is_succeeded:
                    sim_state["current_step"] = "at_pickup"
                    sim_state["step_index"] = 3
                    sim_state["step_title"] = "Chegou ao Ponto de Coleta (pickup_point)"
                    sim_state["step_description"] = f"Robô posicionado no Ponto de Coleta. Clique em 'CONFIRMAR E IR PARA O PRÓXIMO PASSO' para navegar até o destino ({item.upper()})."
                    sim_state["waiting_confirmation"] = True
                else:
                    sim_state["step_title"] = "Falha na navegação (pickup_point)"
                    sim_state["step_description"] = f"Navegação para pickup_point não reportou SUCESSO: {output.strip()[:250]}"
                    sim_state["waiting_confirmation"] = False
            except Exception as e:
                sim_state["step_title"] = "Falha no Undock / Coleta"
                sim_state["step_description"] = f"Erro no passo de coleta: {e}"
                sim_state["last_nav_result"] = "ERROR"
                sim_state["waiting_confirmation"] = False
            finally:
                sim_state["busy"] = False

        threading.Thread(target=_step_pickup, daemon=True).start()
        return {"status": "success", "message": "Avançando para o Ponto de Coleta..."}

    elif step == "at_pickup":
        # Passo 3: Ir para Estação de Entrega / Destino real
        item_map = {
            "blue": "delivery_blue",
            "red": "delivery_red",
            "invalid": "failure_zone",
            "restock": "supply_point"
        }
        target_wp = item_map.get(item, "delivery_blue")
        dx, dy, dyaw = _get_waypoint_pose(target_wp)
        dz, dw = _yaw_to_quaternion(dyaw)

        sim_state["current_step"] = "going_delivery"
        sim_state["step_index"] = 4
        sim_state["step_title"] = f"Indo para Destino ({item.upper()}: {target_wp})"
        sim_state["step_description"] = f"Navegando até o destino '{target_wp}' ({dx}, {dy})..."
        sim_state["waiting_confirmation"] = False
        sim_state["busy"] = True

        def _step_delivery():
            try:
                cmd = f'{JAZZY_ENV_CMD} && ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{{pose: {{header: {{frame_id: map}}, pose: {{position: {{x: {dx}, y: {dy}, z: 0.0}}, orientation: {{z: {dz}, w: {dw}}}}}}}}}"'
                proc = subprocess.Popen(cmd, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                _register_sim_popen(proc)
                try:
                    stdout, _ = proc.communicate(timeout=90.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout = f"Timeout (90s) aguardando chegada a {target_wp}."

                output = stdout or ""
                is_succeeded = ("STATUS_SUCCEEDED" in output or "Goal finished with status SUCCEEDED" in output or "SUCCEEDED" in output) and proc.returncode == 0
                sim_state["last_nav_result"] = "SUCCEEDED" if is_succeeded else "FAILED"

                if is_succeeded:
                    sim_state["current_step"] = "at_delivery"
                    sim_state["step_index"] = 5
                    sim_state["step_title"] = f"Entrega Concluída ({item.upper()})"
                    sim_state["step_description"] = f"Robô chegou a '{target_wp}'. Clique em 'CONFIRMAR E IR PARA O PRÓXIMO PASSO' para retornar à Estação de Carga."
                    sim_state["waiting_confirmation"] = True
                else:
                    sim_state["step_title"] = f"Falha na navegação ({target_wp})"
                    sim_state["step_description"] = f"Navegação para '{target_wp}' não reportou SUCESSO: {output.strip()[:250]}"
                    sim_state["waiting_confirmation"] = False
            except Exception as e:
                sim_state["step_title"] = "Falha na Entrega"
                sim_state["step_description"] = f"Erro no passo de entrega: {e}"
                sim_state["last_nav_result"] = "ERROR"
                sim_state["waiting_confirmation"] = False
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
    _kill_sim_popens()
    sim_state["active"] = False
    sim_state["current_step"] = "idle"
    sim_state["step_title"] = "Simulação Encerrada"
    sim_state["step_description"] = "Modo simulado desativado."
    sim_state["waiting_confirmation"] = False
    sim_state["busy"] = False
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
    """Retorna os últimos logs consultando o Agente do Host."""
    try:
        source_map = {
            "localization": "localization",
            "nav2": "nav2",
            "viz": "viz",
            "mission": "mission_manager",
            "mission_manager": "mission_manager"
        }
        target_source = source_map.get(source, "localization")
        res = _call_host_agent(f"/logs/{target_source}?lines={lines}", method="GET", timeout=4.0)
        return {
            "status": "success",
            "source": source,
            "logs": res.get("logs", [f"Nenhum log retornado pelo agente para {source}."])
        }
    except Exception as e:
        return {
            "status": "error",
            "source": source,
            "logs": [f"Erro ao obter logs do agente do host: {e}"]
        }

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
    x: float
    y: float
    yaw: float

@router.post("/set_initial_pose")
def set_initial_pose(payload: InitialPosePayload):
    """Define a pose no host e so confirma apos evidencia nova do AMCL."""
    if not all(math.isfinite(value) for value in (payload.x, payload.y, payload.yaw)):
        raise HTTPException(status_code=422, detail="X, Y e yaw precisam ser números finitos medidos no mapa.")
    result = _call_host_agent(
        "/ros/set_initial_pose",
        method="POST",
        json_body={"x": payload.x, "y": payload.y, "yaw": payload.yaw},
        timeout=25.0,
    )
    confirmed_pose = result.get("pose")
    source = result.get("confirmation_source")
    covariance = result.get("covariance")
    if confirmed_pose:
        get_turtlebot_node().record_external_amcl_measurement(
            confirmed_pose, covariance, source or "host_amcl_confirmation"
        )
    _nav_readiness_cache["timestamp"] = 0.0
    return {
        "status": "success",
        "message": "Pose inicial recebida e aplicada pelo AMCL no host.",
        "confirmed_pose": confirmed_pose,
        "covariance": covariance,
        "confirmation_source": source,
    }

_dock_lock = threading.Lock()
_undock_lock = threading.Lock()

def _run_create3_dock_action() -> tuple:
    print("[INFO TB4] Disparando ação infravermelha /dock no TurtleBot 4...")
    cmd_action = f'{JAZZY_ENV_CMD} && ros2 action send_goal /dock irobot_create_msgs/action/Dock "{{}}"'
    res = subprocess.run(cmd_action, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
    full_output = res.stdout.strip()
    print(f"[INFO TB4] Resultado do Docking infravermelho: {full_output}")
    is_success = ("SUCCEEDED" in full_output) and not any(k in full_output for k in ["ABORTED", "CANCELED", "FAILED"])
    return is_success, full_output

def _run_create3_undock_action() -> tuple:
    print("[INFO TB4] Disparando ação /undock no TurtleBot 4...")
    cmd_action = f'{JAZZY_ENV_CMD} && ros2 action send_goal /undock irobot_create_msgs/action/Undock "{{}}"'
    res = subprocess.run(cmd_action, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=25)
    full_output = res.stdout.strip()
    print(f"[INFO TB4] Resultado do Undock: {full_output}")
    is_success = ("SUCCEEDED" in full_output) and not any(k in full_output for k in ["ABORTED", "CANCELED", "FAILED"])
    return is_success, full_output

@router.post("/dock")
def trigger_dock():
    """Envia o comando de Docking ao TurtleBot 4.
    
    Se o robô estiver fora da dock e o Nav2 Stack estiver ativo, navega primeiro até 
    o predock_point (-0.5201, -0.0704) e em seguida executa o acoplamento infravermelho.
    Sem guarda de telemetria por decisão de projeto: dock é o caminho de recuperação.
    """
    if not _dock_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Um comando de Docking já está em processamento no robô. Aguarde a manobra finalizar."
        )

    try:
        node = get_turtlebot_node()
        nav_readiness = get_nav_readiness()
        nav_active = bool(nav_readiness.get("checks", {}).get("navigate_to_pose"))
        already_docked = bool(node.is_docked)

        # Se o robô não está dockado e o Nav2 está ativo, executa a Etapa 1 (Nav2 para predock_point)
        if not already_docked and nav_active:
            print("[INFO TB4] Robô fora da dock com Nav2 ativo. Etapa 1/2: Navegando para 'predock_point' (-0.5201, -0.0704)...")
            predock_x = -0.5201
            predock_y = -0.0704
            cmd_nav = f'{JAZZY_ENV_CMD} && ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{{pose: {{header: {{frame_id: map}}, pose: {{position: {{x: {predock_x}, y: {predock_y}, z: 0.0}}, orientation: {{w: 1.0}}}}}}}}"'
            try:
                res_nav = subprocess.run(cmd_nav, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=45)
                nav_out = res_nav.stdout.strip()
                print(f"[INFO TB4] Resultado da navegação ao predock_point: {nav_out}")
            except subprocess.TimeoutExpired:
                print("[WARN TB4] Timeout (45s) na navegação ao predock_point. Tentando alinhamento infravermelho direto...")

        # Etapa 2: Alinhamento Infravermelho Create 3 (/dock)
        is_success, full_output = _run_create3_dock_action()

        if is_success or node.is_docked:
            return {"status": "success", "message": "Docking físico concluído com SUCESSO no TurtleBot 4!"}
        else:
            if not nav_active:
                raise HTTPException(
                    status_code=500,
                    detail="O alinhamento infravermelho local /dock não encontrou a estação de carga. "
                           "O robô parece estar fora do alcance dos sensores infravermelhos da dock. "
                           "Aproxime o robô da estação ou inicie a Localização + Nav2 Stack para navegação autônoma."
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Ação /dock infravermelha não reportou sucesso: {full_output}"
                )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Tempo limite esgotado aguardando a manobra de Docking no robô.")
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
        is_success, full_output = _run_create3_undock_action()

        if is_success or not get_turtlebot_node().is_docked:
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

HOST_AGENT_URL = "http://127.0.0.1:8100"
MISSION_SIGNAL_AGENT_URL = "http://127.0.0.1:8101"

def _load_agent_token() -> str:
    token_file = Path(__file__).resolve().parent.parent / ".agent_token"
    if not token_file.exists():
        token_file = Path("/home/future-lab/B002_Future_Lab_Bots/future_lab_control_center/.agent_token")
    if token_file.exists():
        return token_file.read_text().strip()
    return "futurelab_agent_secret_token_2026_x8100"

AGENT_TOKEN = _load_agent_token()

def _call_host_agent(path: str, method: str = "POST", json_body: dict = None, timeout: float = 10.0):
    import json
    import urllib.request
    import urllib.error
    url = f"{HOST_AGENT_URL}{path}"
    headers = {"X-Agent-Token": AGENT_TOKEN}
    try:
        req = urllib.request.Request(url, headers=headers, method=method)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            req.data = json.dumps(json_body).encode("utf-8")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", "replace")
        try:
            err_json = json.loads(err_msg)
            msg = err_json.get("detail") or err_json.get("message") or str(e)
        except Exception:
            msg = str(e)
        raise HTTPException(status_code=e.code, detail=msg)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Agente do host (127.0.0.1:8100) inacessível: {e}. Execute 'systemctl --user start future-lab-agent' ou o ícone da Área de Trabalho."
        )


def _publish_mission_signal_on_host(signal: str, value: str = "") -> dict:
    """Usa a ponte dedicada do host e exige confirmação da delivery_routine."""
    import json
    import urllib.error
    import urllib.request

    body = json.dumps({"signal": signal, "value": value}).encode("utf-8")
    request = urllib.request.Request(
        f"{MISSION_SIGNAL_AGENT_URL}/publish",
        data=body,
        headers={
            "X-Agent-Token": AGENT_TOKEN,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25.0) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("detail")
        except Exception:
            detail = str(exc)
        raise HTTPException(status_code=exc.code, detail=detail or str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Mission Signal Agent (127.0.0.1:8101) inacessível: {exc}",
        )
    if result.get("received_by_mission") is not True:
        raise HTTPException(
            status_code=504,
            detail="A delivery_routine não confirmou o recebimento do sinal.",
        )
    return result


def _start_test_delivery_on_host(product_class: str) -> dict:
    """Une classe fresca e trigger, exigindo confirmação do destino no host."""
    import json
    import urllib.error
    import urllib.request

    body = json.dumps({"value": product_class}).encode("utf-8")
    request = urllib.request.Request(
        f"{MISSION_SIGNAL_AGENT_URL}/start_delivery",
        data=body,
        headers={
            "X-Agent-Token": AGENT_TOKEN,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25.0) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read().decode("utf-8", "replace"))
            detail = error.get("detail")
        except Exception:
            detail = str(exc)
        raise HTTPException(status_code=exc.code, detail=detail or str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Mission Signal Agent (127.0.0.1:8101) inacessível: {exc}",
        )
    if result.get("started") is not True:
        raise HTTPException(
            status_code=504,
            detail="O destino da delivery não foi confirmado pela rotina.",
        )
    return result


def _trigger_mission_via_host(service_name: str) -> tuple[bool, str]:
    """Usa o participante ROS do host; o container não recebe respostas de serviços."""
    result = _call_host_agent(
        "/ros/trigger_mission",
        method="POST",
        json_body={"service": service_name},
        timeout=55.0,
    )
    if not result.get("responded"):
        return False, result.get("detail", "Serviço ROS não respondeu.")
    return bool(result.get("success")), result.get("message", "")


def _lifecycle_failure_lines(log_text: str) -> list[str]:
    markers = (
        "failed to send response to",
        "Failed to bring up all requested nodes",
        "was unable to be reached",
    )
    return [
        line for line in log_text.splitlines()
        if any(marker in line for marker in markers)
    ][-3:]


def _launch_and_wait_lifecycle(target: str, timeout: float = 90.0):
    """Confirma lifecycle e faz no maximo um retry quando o log prova falha."""
    last_log = ""
    for attempt in (1, 2):
        result = _call_host_agent(f"/launch/{target}", method="POST")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = _call_host_agent("/status", method="GET", timeout=3.0).get(target, {})
            if not status.get("running"):
                raise HTTPException(
                    status_code=500,
                    detail=f"O processo '{target}' terminou antes de o lifecycle ficar ativo.",
                )
            logs_result = _call_host_agent(
                f"/logs/{target}?lines=220", method="GET", timeout=4.0
            )
            last_log = "\n".join(logs_result.get("logs", []))
            if "Managed nodes are active" in last_log:
                result["lifecycle_ready"] = True
                result["attempts"] = attempt
                result["message"] = (
                    f"'{target}' iniciado e lifecycle ROS confirmado como ativo."
                )
                return result

            failures = _lifecycle_failure_lines(last_log)
            if failures:
                # A geracao nao se recupera de resposta change_state perdida ou
                # bringup abortado. Encerra antes de uma unica nova tentativa.
                _call_host_agent(f"/stop/{target}", method="POST", timeout=15.0)
                if attempt == 2:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"'{target}' falhou no lifecycle em duas geracoes controladas. "
                            "Nenhum processo incompleto foi mantido. Evidencias: "
                            + " | ".join(failures)
                        ),
                    )
                time.sleep(1.0)
                break
            time.sleep(1.0)
        else:
            relevant = [
                line for line in last_log.splitlines()
                if "Waiting for service" in line
            ][-3:]
            detail = (
                f"O processo '{target}' existe, mas o lifecycle nao ficou ativo em "
                f"{timeout:.0f}s. Nao inicie outra copia."
            )
            if relevant:
                detail += " Ultimas evidencias: " + " | ".join(relevant)
            raise HTTPException(status_code=504, detail=detail)

    raise HTTPException(status_code=500, detail=f"Falha inesperada ao iniciar '{target}'.")

@router.post("/launch_localization")
def launch_localization():
    """Inicia uma geracao e so confirma apos map_server e AMCL ativos."""
    result = _launch_and_wait_lifecycle("localization")
    get_turtlebot_node().clear_amcl_measurement()
    _processes_cache["timestamp"] = 0.0
    _nav_readiness_cache["timestamp"] = 0.0
    return result

@router.post("/launch_nav2")
def launch_nav2():
    """Inicia uma geracao e so confirma apos os managed nodes ativos."""
    host_status = _call_host_agent("/status", method="GET", timeout=3.0)
    current = host_status.get("nav2", {})
    if isinstance(current, dict) and current.get("running"):
        raise HTTPException(
            status_code=409,
            detail=("Nav2 já está ativo; nenhuma nova geração foi criada. "
                    f"PID principal: {current.get('pid')}."),
        )

    node = get_turtlebot_node()
    if not node.telemetry_fresh():
        raise HTTPException(
            status_code=503,
            detail="Telemetria da Create 3 está ausente; Nav2 não foi iniciado.",
        )
    if node.is_docked is not False:
        raise HTTPException(
            status_code=409,
            detail=("Nav2 não foi iniciado: enquanto dockada, a Create 3 suspende "
                    "odom→base_link e o lifecycle aborta no planner_server. Faça um "
                    "Undock autorizado, aguarde scan/odom/TF e tente novamente."),
        )

    scan_status = node.get_scan_status()
    if not scan_status.get("fresh"):
        raise HTTPException(
            status_code=409,
            detail=f"Nav2 não foi iniciado: {scan_status.get('reason') or '/scan não está fresco'}.",
        )

    amcl_status = node.get_amcl()
    if not amcl_status.get("initialized"):
        raise HTTPException(
            status_code=409,
            detail=("Nav2 não foi iniciado: nenhuma pose inicial foi confirmada pelo AMCL. "
                    "Defina a pose inicial e tente novamente."),
        )

    result = _launch_and_wait_lifecycle("nav2")
    _processes_cache["timestamp"] = 0.0
    _nav_readiness_cache["timestamp"] = 0.0
    return result

@router.post("/launch_viz")
def launch_viz():
    """Inicia uma unica instancia do RViz no host."""
    result = _call_host_agent("/launch/viz", method="POST")
    _processes_cache["timestamp"] = 0.0
    return result

@router.post("/stop_localization")
def stop_localization():
    """Encerra e confirma a ausencia de map_server, AMCL e lifecycle manager."""
    result = _call_host_agent("/stop/localization", method="POST", timeout=12.0)
    get_turtlebot_node().clear_amcl_measurement()
    _processes_cache["timestamp"] = 0.0
    _nav_readiness_cache["timestamp"] = 0.0
    return result

@router.post("/stop_nav2")
def stop_nav2():
    """Encerra e confirma a ausencia dos processos da navegacao."""
    result = _call_host_agent("/stop/nav2", method="POST", timeout=12.0)
    _processes_cache["timestamp"] = 0.0
    _nav_readiness_cache["timestamp"] = 0.0
    return result

@router.post("/stop_viz")
def stop_viz():
    """Encerra e confirma a ausencia do RViz."""
    result = _call_host_agent("/stop/viz", method="POST", timeout=12.0)
    _processes_cache["timestamp"] = 0.0
    return result

@router.post("/launch_mission_manager")
def launch_mission_manager():
    """Inicia uma unica instancia do Mission Manager."""
    result = _call_host_agent("/launch/mission_manager", method="POST")
    _processes_cache["timestamp"] = 0.0
    return result

@router.post("/stop_mission_manager_process")
def stop_mission_manager_process():
    """Encerra e confirma a ausencia do Mission Manager."""
    result = _call_host_agent("/stop/mission_manager", method="POST", timeout=12.0)
    _processes_cache["timestamp"] = 0.0
    return result

@router.post("/trigger_delivery")
def trigger_delivery():
    """Aciona o serviço ROS 2 de entrega de peças (/start_delivery)."""
    _require_live_telemetry()
    _require_mission_ready()
    ok, msg = _trigger_mission_via_host("start_delivery")
    if not ok:
        raise HTTPException(status_code=503, detail=msg)
    return {"status": "success", "message": msg or "Rotina de Entrega acionada!"}


@router.post("/mission_test/product_class")
def publish_mission_test_product_class(payload: MissionTestClassSchema):
    """Publica somente uma classificação sintética; não move nenhum robô."""
    aliases = {
        "blue": "tin_valid_blue",
        "tin_valid_blue": "tin_valid_blue",
        "red": "tin_valid_red",
        "tin_valid_red": "tin_valid_red",
    }
    requested = str(payload.item or "").strip().lower()
    product_class = aliases.get(requested)
    if product_class is None:
        raise HTTPException(
            status_code=422,
            detail="Classe de teste inválida. Use somente 'blue' ou 'red'.",
        )

    result = _publish_mission_signal_on_host("product_class", product_class)
    return {
        **result,
        "status": "received",
        "message": (
            f"Classe sintética '{product_class}' recebida e registrada pela rotina "
            "de missão no host."
        ),
    }


@router.post("/mission_test/start_delivery")
def start_mission_test_delivery(payload: MissionTestClassSchema):
    """Simula a visão do cobot e inicia delivery com classe fresca confirmada."""
    _require_live_telemetry()
    _require_mission_ready()
    aliases = {
        "blue": "tin_valid_blue",
        "tin_valid_blue": "tin_valid_blue",
        "red": "tin_valid_red",
        "tin_valid_red": "tin_valid_red",
    }
    requested = str(payload.item or "").strip().lower()
    product_class = aliases.get(requested)
    if product_class is None:
        raise HTTPException(
            status_code=422,
            detail="Classe de teste inválida. Use somente 'blue' ou 'red'.",
        )
    result = _start_test_delivery_on_host(product_class)
    return {
        **result,
        "status": "started",
        "message": (
            f"Delivery iniciada com '{product_class}' e destino "
            f"'{result['target']}' confirmado no log da rotina."
        ),
    }


@router.post("/mission_test/item_released")
def publish_mission_test_item_released():
    """Publica somente o sinal sintético de lata liberada; não move o cobot."""
    result = _publish_mission_signal_on_host("item_released", "")
    return {
        **result,
        "status": "received",
        "message": "Liberação sintética recebida e confirmada pela rotina de missão.",
    }

@router.post("/trigger_failure")
def trigger_failure():
    """Aciona o serviço ROS 2 de recolhimento de peça com defeito / descarte (/start_failure)."""
    _require_live_telemetry()
    _require_mission_ready()
    ok, msg = _trigger_mission_via_host("start_failure")
    if not ok:
        raise HTTPException(status_code=503, detail=msg)
    return {"status": "success", "message": msg or "Rotina de Falha/Descarte acionada!"}

@router.post("/trigger_restock")
def trigger_restock():
    """Aciona o serviço ROS 2 de reabastecimento de matéria-prima (/start_restock)."""
    _require_live_telemetry()
    _require_mission_ready()
    ok, msg = _trigger_mission_via_host("start_restock")
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
    """Interrompe a missão ativa e força parada dos motores. Retorna status transparente."""
    node = get_turtlebot_node()
    avisos = []

    # 1. Cancelar todas as metas do /navigate_to_pose via serviço CancelGoal
    cancel_ok, cancel_count, cancel_err = node.cancel_all_nav_goals(timeout_sec=3.0, confirm_sec=5.0)
    if cancel_err:
        avisos.append(cancel_err)

    # 2. Matar subprocessos Popen do modo simulado
    killed_sim_procs = _kill_sim_popens()

    # 3. Desativar estado do modo simulado
    sim_state["active"] = False
    sim_state["busy"] = False
    sim_state["waiting_confirmation"] = False

    # 4. Chamar serviço /stop_mission do Mission Manager
    try:
        mm_ok, mm_msg = _trigger_mission_via_host("stop_mission")
    except HTTPException as exc:
        mm_ok, mm_msg = False, str(exc.detail)
    if not mm_ok:
        avisos.append(f"Mission Manager não estava no ar — nenhuma missão para cancelar.")

    # 5. Rajada de zero como impulso secundário: 20 Hz por 2.0 s (40 mensagens)
    # Nota: Com o Nav2 ativo, o controller_server reescreve /cmd_vel no ciclo seguinte. O freio real e o cancelamento de meta acima.
    zero_requested = node.send_cmd_vel(0.0, 0.0, duration_sec=2.0, hz=20.0)
    if not zero_requested:
        avisos.append("Publishers de velocidade indisponiveis; comando zero nao foi enviado.")

    overall_status = "success" if cancel_ok else "partial"
    msg = "🛑 Cancelamento da meta confirmado; comando de velocidade zero solicitado."
    if overall_status == "partial":
        msg = ("⚠️ NÃO FOI POSSÍVEL CONFIRMAR O CANCELAMENTO DA META. "
               "Se o robô estiver em movimento, use o botão físico da Create 3.")

    return {
        "status": overall_status,
        "message": msg,
        "nav_goal_cancelada": cancel_ok,
        "processos_simulacao_mortos": killed_sim_procs,
        "mission_manager_ok": mm_ok,
        "cmd_vel_zero_solicitado": zero_requested,
        "avisos": avisos
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

# ============================================================
# Rotas de Recuperação do Sistema (Fase 13d)
# ============================================================
@router.get("/system/inventory")
def get_system_inventory():
    """Consulta o inventário de saúde do sistema de 10 itens via Agente do Host."""
    return _call_host_agent("/system/inventory", method="GET")

@router.post("/system/restart_backend")
def system_restart_backend():
    """Reinicia o container do backend via Agente do Host."""
    return _call_host_agent("/system/restart_backend", method="POST")

@router.post("/system/restart_cobot_discovery")
def system_restart_cobot_discovery():
    """Reinicia o Discovery Server do myCobot (:11888) via Agente do Host."""
    return _call_host_agent("/system/restart_cobot_discovery", method="POST")

@router.post("/robot/restart_bringup")
def robot_restart_bringup():
    """Reinicia o serviço turtlebot4.service no RPi4 via SSH através do Agente do Host."""
    return _call_host_agent("/robot/restart_bringup", method="POST")

@router.post("/robot/start_oakd")
def robot_start_oakd():
    """Desperta a câmera OAK-D no RPi4 via SSH através do Agente do Host."""
    return _call_host_agent("/robot/start_oakd", method="POST")
