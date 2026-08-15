#!/usr/bin/env python3
"""Future Lab Host Agent (127.0.0.1:8100).

Gerencia Localizacao, Nav2, RViz e Mission Manager no host. Cada alvo e
executado em seu proprio grupo de processos. Um stop so retorna sucesso depois
que todos os processos daquele alvo realmente desapareceram.
"""

from __future__ import annotations

import json
import math
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Dict, Iterable, Optional
from urllib.parse import parse_qs, urlparse


REPO_DIR = Path(__file__).resolve().parent.parent.parent
TOKEN_FILE = REPO_DIR / "future_lab_control_center" / ".agent_token"
TB4_WS = REPO_DIR / "turtlebot4_jazzy"
DOCKER_COMPOSE_FILE = REPO_DIR / "future_lab_control_center" / "docker-compose.yml"
INITIAL_POSE_HELPER = REPO_DIR / "future_lab_control_center" / "host_agent" / "initial_pose_once.py"
TRIGGER_SERVICE_HELPER = REPO_DIR / "future_lab_control_center" / "host_agent" / "trigger_service_once.py"

TRIGGER_SERVICES = {
    "start_delivery": "/start_delivery",
    "start_failure": "/start_failure",
    "start_restock": "/start_restock",
    "stop_mission": "/stop_mission",
}
TRIGGER_SERVICE_LOCK = threading.Lock()

JAZZY_ENV_CMD = (
    "source /opt/ros/jazzy/setup.bash && "
    f"source {TB4_WS}/setup.bash && "
    "unset ROS_AUTOMATIC_DISCOVERY_RANGE && "
    "export ROS_DOMAIN_ID=0 && "
    "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && "
    "export ROS_SUPER_CLIENT=True && "
    "export ROS_DISCOVERY_SERVER='192.168.0.129:11811;' && "
    "export DISPLAY=:0 && "
    "export LIBGL_ALWAYS_SOFTWARE=1 && "
    "export QT_X11_NO_MITSHM=1"
)


def load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return "futurelab_agent_secret_token_2026_x8100"


AGENT_TOKEN = load_token()


@dataclass(frozen=True)
class LaunchSpec:
    command: str
    log_path: Path
    markers: tuple[str, ...]
    needs_xhost: bool = False


LAUNCH_SPECS: Dict[str, LaunchSpec] = {
    "localization": LaunchSpec(
        command=(
            f"{JAZZY_ENV_CMD} && exec ros2 launch "
            f"{TB4_WS}/launch/localization_lifecycle_timeout.launch.py "
            f"map:={TB4_WS}/maps/B002_map.yaml use_sim_time:=false "
            "autostart:=true bond_timeout:=30.0 lifecycle_start_delay:=10.0"
        ),
        log_path=Path("/tmp/nav2_localization.log"),
        markers=(
            "localization_lifecycle_timeout.launch.py",
            "/nav2_map_server/map_server",
            "/nav2_amcl/amcl",
            "lifecycle_manager_localization",
        ),
    ),
    "nav2": LaunchSpec(
        command=(
            f"{JAZZY_ENV_CMD} && exec ros2 launch "
            f"{TB4_WS}/launch/nav2_lifecycle_timeout.launch.py "
            f"params_file:={TB4_WS}/config/nav2_custom.yaml "
            "use_sim_time:=false autostart:=true bond_timeout:=30.0 "
            "lifecycle_start_delay:=10.0"
        ),
        log_path=Path("/tmp/nav2_stack.log"),
        markers=(
            "nav2_lifecycle_timeout.launch.py",
            "/nav2_controller/controller_server",
            "/nav2_planner/planner_server",
            "/nav2_bt_navigator/bt_navigator",
            "/nav2_behaviors/behavior_server",
            "/nav2_smoother/smoother_server",
            "/nav2_route/route_server",
            "/nav2_waypoint_follower/waypoint_follower",
            "/nav2_velocity_smoother/velocity_smoother",
            "/nav2_collision_monitor/collision_monitor",
            "/opennav_docking/",
            "lifecycle_manager_navigation",
        ),
    ),
    "viz": LaunchSpec(
        command=(
            f"{JAZZY_ENV_CMD} && exec ros2 launch turtlebot4_viz "
            "view_navigation.launch.py use_sim_time:=false"
        ),
        log_path=Path("/tmp/nav2_viz.log"),
        markers=("view_navigation.launch.py", "/rviz2/rviz2"),
        needs_xhost=True,
    ),
    "mission_manager": LaunchSpec(
        command=(
            f"{JAZZY_ENV_CMD} && export PYTHONUNBUFFERED=1 && "
            "exec python3 -u scripts/mission_manager.py --ros-args "
            "--params-file params/waypoints.yaml"
        ),
        log_path=Path("/tmp/nav2_mission_manager.log"),
        markers=("scripts/mission_manager.py",),
    ),
}

LOG_FILES = {name: str(spec.log_path) for name, spec in LAUNCH_SPECS.items()}


class ProcessConflict(RuntimeError):
    def __init__(self, target: str, status: dict):
        super().__init__(f"'{target}' ja esta ativo")
        self.target = target
        self.status = status


class StopFailed(RuntimeError):
    def __init__(self, target: str, details: dict):
        super().__init__(f"nao foi possivel encerrar todos os processos de '{target}'")
        self.target = target
        self.details = details


def _read_process(pid: int) -> tuple[list[str], str, str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        cmdline = " ".join(argv)
        try:
            executable = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            executable = argv[0] if argv else ""
        return argv, executable, cmdline
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return [], "", ""


def _iter_processes() -> Iterable[tuple[int, int, list[str], str, str]]:
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        argv, executable, cmdline = _read_process(pid)
        if not cmdline:
            continue
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue
        yield pid, pgid, argv, executable, cmdline


def _is_ros2_launch(argv: list[str], package: str, launch_file: str) -> bool:
    try:
        idx = argv.index("launch")
    except ValueError:
        return False
    return argv[idx + 1:idx + 3] == [package, launch_file]


def _matches(target: str, spec: LaunchSpec, argv: list[str], executable: str, cmdline: str) -> bool:
    """Reconhece executaveis/argv reais; texto solto de ps/grep nao conta."""
    exe = executable.removesuffix(" (deleted)")
    exe_name = Path(exe).name

    # Suporte aos processos controlados nos testes unitarios.
    if target not in LAUNCH_SPECS:
        return any(marker in argv for marker in spec.markers)

    if target == "localization":
        if _is_ros2_launch(argv, "turtlebot4_navigation", "localization.launch.py"):
            return True
        if any(arg.endswith("/localization_lifecycle_timeout.launch.py") for arg in argv):
            return exe_name.startswith("python")
        if exe.endswith(("/nav2_map_server/map_server", "/nav2_amcl/amcl")):
            return True
        if exe.endswith("/nav2_lifecycle_manager/lifecycle_manager"):
            return "lifecycle_manager_localization" in cmdline
        return exe_name in {"bash", "sh"} and (
            "ros2 launch turtlebot4_navigation localization.launch.py" in cmdline
            or "localization_lifecycle_timeout.launch.py" in cmdline
        )

    if target == "nav2":
        if _is_ros2_launch(argv, "turtlebot4_navigation", "nav2.launch.py"):
            return True
        if any(arg.endswith("/nav2_lifecycle_timeout.launch.py") for arg in argv):
            return exe_name.startswith("python")
        nav_executables = (
            "/nav2_controller/controller_server",
            "/nav2_planner/planner_server",
            "/nav2_bt_navigator/bt_navigator",
            "/nav2_behaviors/behavior_server",
            "/nav2_smoother/smoother_server",
            "/nav2_route/route_server",
            "/nav2_waypoint_follower/waypoint_follower",
            "/nav2_velocity_smoother/velocity_smoother",
            "/nav2_collision_monitor/collision_monitor",
            "/opennav_docking/opennav_docking",
            "/opennav_docking/docking_server",
        )
        if exe.endswith(nav_executables):
            return True
        if exe.endswith("/nav2_lifecycle_manager/lifecycle_manager"):
            return "lifecycle_manager_navigation" in cmdline
        return exe_name in {"bash", "sh"} and (
            "ros2 launch turtlebot4_navigation nav2.launch.py" in cmdline
            or "nav2_lifecycle_timeout.launch.py" in cmdline
        )

    if target == "viz":
        if _is_ros2_launch(argv, "turtlebot4_viz", "view_navigation.launch.py"):
            return True
        if exe.endswith("/rviz2/rviz2"):
            return True
        return exe_name in {"bash", "sh"} and "ros2 launch turtlebot4_viz view_navigation.launch.py" in cmdline

    if target == "mission_manager":
        if any(arg.endswith("/scripts/mission_manager.py") or arg == "scripts/mission_manager.py" for arg in argv):
            return exe_name.startswith("python")
        return exe_name in {"bash", "sh"} and "python3 -u scripts/mission_manager.py" in cmdline

    return False


class ProcessManager:
    """Gerencia grupos de processo e confirma start/stop pelo estado de /proc."""

    def __init__(self, specs: Optional[Dict[str, LaunchSpec]] = None):
        self.specs = specs or LAUNCH_SPECS
        self._owned: Dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def _target_processes(self, target: str) -> list[dict]:
        spec = self.specs[target]
        found = []
        for pid, pgid, argv, executable, cmdline in _iter_processes():
            if _matches(target, spec, argv, executable, cmdline):
                found.append({"pid": pid, "pgid": pgid, "cmdline": cmdline})
        return sorted(found, key=lambda item: item["pid"])

    def _group_members(self, pgid: int) -> list[dict]:
        return [
            {"pid": pid, "pgid": proc_pgid, "cmdline": cmdline}
            for pid, proc_pgid, _argv, _executable, cmdline in _iter_processes()
            if proc_pgid == pgid
        ]

    def _group_is_safe_for_target(self, target: str, pgid: int) -> tuple[bool, list[dict]]:
        """Evita matar um terminal/grupo que tambem contenha processos alheios."""
        spec = self.specs[target]
        members = self._group_members(pgid)
        if not members or pgid in (0, 1, os.getpgrp()):
            return False, members
        safe = True
        for item in members:
            argv, executable, cmdline = _read_process(item["pid"])
            if not _matches(target, spec, argv, executable, cmdline):
                safe = False
                break
        return safe, members

    def _group_exists(self, pgid: int) -> bool:
        # /proc/<pid>/cmdline fica vazio para zombies. Eles ja nao executam nem
        # mantem participantes DDS, e serao coletados por Popen.wait logo abaixo.
        return bool(self._group_members(pgid))

    def _wait_group_gone(self, pgid: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._group_exists(pgid):
                return True
            time.sleep(0.05)
        return not self._group_exists(pgid)

    def status(self, target: str) -> dict:
        with self._lock:
            proc = self._owned.get(target)
            if proc is not None and proc.poll() is not None:
                self._owned.pop(target, None)
                proc = None

            found = self._target_processes(target)
            pgids = sorted({item["pgid"] for item in found})
            owned_pgid = proc.pid if proc is not None else None
            owned = bool(proc is not None and owned_pgid in pgids)
            error = None
            if len(pgids) > 1:
                error = f"{len(pgids)} instancias concorrentes detectadas"

            return {
                "running": bool(found),
                "pid": proc.pid if owned else (found[0]["pid"] if found else None),
                "pgid": owned_pgid if owned else (pgids[0] if len(pgids) == 1 else None),
                "owned": owned,
                "instances": len(pgids),
                "pids": [item["pid"] for item in found],
                "error": error,
            }

    def status_all(self) -> dict:
        return {target: self.status(target) for target in self.specs}

    def start(self, target: str) -> dict:
        with self._lock:
            current = self.status(target)
            if current["running"]:
                raise ProcessConflict(target, current)

            spec = self.specs[target]
            if spec.needs_xhost:
                subprocess.run(
                    ["xhost", "+local:root"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                    check=False,
                )

            spec.log_path.parent.mkdir(parents=True, exist_ok=True)
            with spec.log_path.open("w", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    ["/bin/bash", "-lc", spec.command],
                    cwd=str(TB4_WS),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            self._owned[target] = proc

            confirm_deadline = time.monotonic() + 5.0
            measured = self.status(target)
            while not measured["running"] and time.monotonic() < confirm_deadline:
                exit_code = proc.poll()
                if exit_code is not None:
                    self._owned.pop(target, None)
                    tail = ""
                    try:
                        tail = "\n".join(spec.log_path.read_text(errors="replace").splitlines()[-20:])
                    except OSError:
                        pass
                    raise RuntimeError(
                        f"'{target}' terminou durante o start (exit={exit_code}). {tail}".strip()
                    )
                time.sleep(0.1)
                measured = self.status(target)
            if not measured["running"] or measured["instances"] != 1:
                # Este grupo acabou de ser criado pelo agente; encerra pelo
                # PGID conhecido mesmo se o argv ainda estiver entre bash/exec.
                self._stop_group(proc.pid)
                self._owned.pop(target, None)
                raise RuntimeError(f"start de '{target}' nao foi confirmado: {measured}")

            return {
                "status": "process_started",
                "message": (
                    f"Processo '{target}' iniciado; aguarde a validacao do lifecycle ROS antes de usa-lo."
                ),
                "process": measured,
            }

    def _stop_group(self, pgid: int) -> list[str]:
        signals_sent: list[str] = []
        for sig, name, timeout in (
            (signal.SIGINT, "SIGINT", 5.0),
            (signal.SIGTERM, "SIGTERM", 3.0),
            (signal.SIGKILL, "SIGKILL", 1.0),
        ):
            if not self._group_exists(pgid):
                break
            os.killpg(pgid, sig)
            signals_sent.append(name)
            if self._wait_group_gone(pgid, timeout):
                break
        return signals_sent

    def stop(self, target: str) -> dict:
        with self._lock:
            before = self._target_processes(target)
            groups = sorted({item["pgid"] for item in before})
            if not groups:
                self._owned.pop(target, None)
                return {
                    "status": "already_stopped",
                    "message": f"Processo '{target}' ja estava parado.",
                    "stopped_groups": [],
                    "signals": {},
                    "survivors": [],
                }

            unsafe_groups = []
            for pgid in groups:
                safe, members = self._group_is_safe_for_target(target, pgid)
                if not safe:
                    unsafe_groups.append({"pgid": pgid, "members": members})
            if unsafe_groups:
                details = {
                    "unsafe_groups": unsafe_groups,
                    "survivors": [item["pid"] for item in before],
                }
                raise StopFailed(target, details)

            sent: Dict[str, list[str]] = {}
            for pgid in groups:
                try:
                    sent[str(pgid)] = self._stop_group(pgid)
                except ProcessLookupError:
                    sent[str(pgid)] = []

            proc = self._owned.pop(target, None)
            if proc is not None:
                try:
                    proc.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass

            survivors = self._target_processes(target)
            if survivors:
                raise StopFailed(
                    target,
                    {
                        "stopped_groups": groups,
                        "signals": sent,
                        "survivors": survivors,
                    },
                )

            return {
                "status": "stopped",
                "message": f"Processo '{target}' encerrado e ausencia confirmada no host.",
                "stopped_groups": groups,
                "signals": sent,
                "survivors": [],
            }

    def stop_all(self) -> dict:
        results = {}
        errors = {}
        for target in self.specs:
            try:
                results[target] = self.stop(target)
            except StopFailed as exc:
                errors[target] = exc.details
        return {"results": results, "errors": errors, "ok": not errors}


PROCESS_MANAGER = ProcessManager()


def run_initial_pose(x: float, y: float, yaw: float, timeout: float = 15.0) -> tuple[dict, int]:
    """Executa a publicacao no host e exige evidencia nova do proprio AMCL."""
    if not all(math.isfinite(value) for value in (x, y, yaw)):
        return {"detail": "X, Y e yaw precisam ser numeros finitos medidos no mapa."}, 422

    command = (
        f"{JAZZY_ENV_CMD} && exec python3 '{INITIAL_POSE_HELPER}' "
        '--x "$1" --y "$2" --yaw "$3" --timeout "$4"'
    )
    try:
        completed = subprocess.run(
            [
                "/bin/bash", "-lc", command, "initial-pose",
                str(x), str(y), str(yaw), str(timeout),
            ],
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=timeout + 8.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"detail": "Timeout esperando confirmacao da pose inicial pelo AMCL."}, 504
    except OSError as exc:
        return {"detail": f"Falha ao executar helper de pose inicial: {exc}"}, 500

    result = None
    for line in reversed(completed.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            result = candidate
            break
    if result is None:
        diagnostic = (completed.stderr or completed.stdout).strip()[-1000:]
        return {
            "detail": "Helper de pose inicial terminou sem resposta JSON mensuravel.",
            "diagnostic": diagnostic,
        }, 500
    if completed.returncode != 0 or not result.get("ok"):
        return {
            "detail": result.get("error", "AMCL nao confirmou a pose inicial."),
            "measurement": result,
        }, 503
    return result, 200


def run_trigger_service(
    service_name: str,
    discovery_timeout: float = 20.0,
    response_timeout: float = 20.0,
) -> tuple[dict, int]:
    """Chama uma vez um Trigger permitido e exige a resposta real do servidor."""
    service_path = TRIGGER_SERVICES.get(service_name)
    if service_path is None:
        return {"detail": f"Trigger '{service_name}' não permitido."}, 422

    command = (
        f"{JAZZY_ENV_CMD} && exec python3 '{TRIGGER_SERVICE_HELPER}' "
        '--service "$1" --discovery-timeout "$2" --response-timeout "$3"'
    )
    try:
        with TRIGGER_SERVICE_LOCK:
            completed = subprocess.run(
                [
                    "/bin/bash", "-lc", command, "trigger-service",
                    service_path, str(discovery_timeout), str(response_timeout),
                ],
                cwd=str(REPO_DIR),
                capture_output=True,
                text=True,
                timeout=discovery_timeout + response_timeout + 10.0,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return {
            "detail": (
                f"Helper de '{service_path}' excedeu o prazo; o estado da requisição "
                "é indeterminado e ela não deve ser repetida automaticamente."
            )
        }, 504
    except OSError as exc:
        return {"detail": f"Falha ao executar helper de trigger: {exc}"}, 500

    result = None
    for line in reversed(completed.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            result = candidate
            break

    if result is None:
        diagnostic = (completed.stderr or completed.stdout).strip()[-1000:]
        return {
            "detail": "Helper de trigger terminou sem resposta JSON mensurável.",
            "diagnostic": diagnostic,
        }, 500
    if completed.returncode != 0 or not result.get("responded"):
        result["detail"] = result.get("error", "Serviço ROS não respondeu.")
        return result, 504 if result.get("request_sent") else 503
    return result, 200


def check_port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class AgentRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict, code: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _verify_token(self) -> bool:
        token = self.headers.get("X-Agent-Token", "").strip()
        if token != AGENT_TOKEN:
            self._send_json({"detail": "Token de agente invalido ou ausente (X-Agent-Token)."}, 401)
            return False
        return True

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length invalido.") from exc
        if length < 1 or length > 8192:
            raise ValueError("Corpo JSON ausente ou maior que 8192 bytes.")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Corpo JSON invalido.") from exc
        if not isinstance(body, dict):
            raise ValueError("O corpo JSON precisa ser um objeto.")
        return body

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({"ok": True, "display": os.environ.get("DISPLAY", ":0"), "timestamp": time.time()})
            return
        if not self._verify_token():
            return

        if path == "/status":
            self._send_json(PROCESS_MANAGER.status_all())
            return

        if path.startswith("/logs/"):
            target = path[len("/logs/"):]
            if target not in LOG_FILES:
                self._send_json({"detail": f"Alvo de log '{target}' desconhecido."}, 404)
                return
            log_path = Path(LOG_FILES[target])
            try:
                lines_count = max(1, min(1000, int(query.get("lines", ["50"])[0])))
            except ValueError:
                lines_count = 50
            if not log_path.exists():
                self._send_json({"status": "success", "source": target, "logs": [f"Arquivo {log_path} ainda nao existe."]})
                return
            try:
                lines = log_path.read_text(errors="replace").splitlines()[-lines_count:]
                self._send_json({"status": "success", "source": target, "logs": lines})
            except OSError as exc:
                self._send_json({"detail": f"Falha ao ler {log_path}: {exc}"}, 500)
            return

        if path == "/system/inventory":
            items = []
            docker_active = subprocess.run(["systemctl", "is-active", "docker"], capture_output=True, text=True).stdout.strip() == "active"
            items.append({"id": 1, "name": "Docker Daemon", "host": "PC Host", "ok": docker_active, "action": "none"})
            for item_id, name, container in (
                (2, "Container Backend", "future_lab_backend"),
                (3, "Container Frontend", "future_lab_frontend"),
            ):
                res = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container], capture_output=True, text=True)
                items.append({"id": item_id, "name": name, "host": "PC Host", "ok": res.stdout.strip() == "true", "action": "restart_backend" if item_id == 2 else "none"})
            items.extend([
                {"id": 4, "name": "Discovery Server Cobot (:11888)", "host": "PC Host", "ok": check_port_open("127.0.0.1", 11888), "action": "restart_cobot_discovery"},
                {"id": 5, "name": "Agente do Host (:8100)", "host": "PC Host", "ok": True, "action": "none"},
                {"id": 6, "name": "Sessao Grafica X11 (:0)", "host": "PC Host", "ok": bool(os.environ.get("DISPLAY")), "action": "none"},
            ])
            tb4_ping = subprocess.run(["ping", "-c", "1", "-w", "2", "192.168.0.129"], capture_output=True).returncode == 0
            items.extend([
                {"id": 7, "name": "TurtleBot 4 Service (RPi4)", "host": "192.168.0.129", "ok": tb4_ping, "action": "restart_tb4_bringup"},
                {"id": 8, "name": "Discovery Server TB4 (:11811)", "host": "192.168.0.129", "ok": check_port_open("192.168.0.129", 11811), "action": "none"},
                {"id": 9, "name": "Create 3 Base (usb0)", "host": "192.168.186.2", "ok": tb4_ping, "action": "none"},
                {"id": 10, "name": "Jetson Nano Stream (:8080)", "host": "192.168.0.250", "ok": check_port_open("192.168.0.250", 8080), "action": "none"},
            ])
            self._send_json(items)
            return

        self._send_json({"detail": "Rota GET nao encontrada."}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._verify_token():
            return

        if path == "/ros/set_initial_pose":
            try:
                body = self._read_json()
                raw_values = (body.get("x"), body.get("y"), body.get("yaw"))
                if any(isinstance(value, bool) for value in raw_values):
                    raise ValueError("X, Y e yaw precisam ser numeros.")
                x, y, yaw = (float(value) for value in raw_values)
            except (TypeError, ValueError) as exc:
                self._send_json({"detail": str(exc)}, 422)
                return
            result, code = run_initial_pose(x, y, yaw)
            self._send_json(result, code)
            return

        if path == "/ros/trigger_mission":
            try:
                body = self._read_json()
                service_name = str(body.get("service", ""))
            except ValueError as exc:
                self._send_json({"detail": str(exc)}, 422)
                return
            result, code = run_trigger_service(service_name)
            self._send_json(result, code)
            return

        if path.startswith("/launch/"):
            target = path[len("/launch/"):]
            if target not in LAUNCH_SPECS:
                self._send_json({"detail": f"Alvo '{target}' desconhecido."}, 404)
                return
            try:
                self._send_json(PROCESS_MANAGER.start(target), 202)
            except ProcessConflict as exc:
                self._send_json({"detail": str(exc), "process": exc.status}, 409)
            except Exception as exc:
                self._send_json({"detail": f"Falha ao iniciar '{target}': {type(exc).__name__}: {exc}"}, 500)
            return

        if path.startswith("/stop/"):
            target = path[len("/stop/"):]
            if target not in LAUNCH_SPECS:
                self._send_json({"detail": f"Alvo '{target}' desconhecido."}, 404)
                return
            try:
                self._send_json(PROCESS_MANAGER.stop(target))
            except StopFailed as exc:
                self._send_json({"detail": str(exc), **exc.details}, 500)
            except Exception as exc:
                self._send_json({"detail": f"Falha ao encerrar '{target}': {type(exc).__name__}: {exc}"}, 500)
            return

        if path == "/system/restart_backend":
            try:
                subprocess.Popen(
                    ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "restart", "backend"],
                    cwd=str(DOCKER_COMPOSE_FILE.parent),
                    start_new_session=True,
                )
                self._send_json({"status": "accepted", "message": "Reinicio do backend solicitado."}, 202)
            except Exception as exc:
                self._send_json({"detail": f"Falha ao reiniciar backend: {exc}"}, 500)
            return

        if path == "/system/restart_cobot_discovery":
            res = subprocess.run(
                ["systemctl", "--user", "restart", "future-lab-cobot-discovery"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0:
                self._send_json({"status": "success", "message": "Discovery Server do cobot reiniciado."})
            else:
                self._send_json({"detail": res.stderr.strip() or res.stdout.strip()}, 500)
            return

        if path == "/robot/restart_bringup":
            res = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "ubuntu@192.168.0.129", "sudo -n systemctl restart turtlebot4.service"],
                capture_output=True,
                text=True,
                timeout=45,
            )
            if res.returncode == 0:
                self._send_json({"status": "success", "message": "turtlebot4.service reiniciado no Raspberry Pi."})
            else:
                self._send_json({"detail": res.stderr.strip() or res.stdout.strip()}, 500)
            return

        if path == "/robot/start_oakd":
            res = subprocess.run(
                [
                    "ssh", "-o", "ConnectTimeout=5", "ubuntu@192.168.0.129",
                    "source /etc/turtlebot4/setup.bash && ros2 service call /oakd/start_camera std_srvs/srv/Trigger {}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode == 0:
                self._send_json({"status": "success", "message": "Camera OAK-D ativada via ROS 2."})
            else:
                self._send_json({"detail": res.stderr.strip() or res.stdout.strip()}, 500)
            return

        self._send_json({"detail": "Rota POST nao encontrada."}, 404)


def _cleanup_cli() -> int:
    result = PROCESS_MANAGER.stop_all()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        raise SystemExit(_cleanup_cli())

    server = ThreadedHTTPServer(("127.0.0.1", 8100), AgentRequestHandler)
    print("[INFO] Future Lab Host Agent em http://127.0.0.1:8100")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
