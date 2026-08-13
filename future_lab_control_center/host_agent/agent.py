#!/usr/bin/env python3
"""
Future Lab Host Agent (127.0.0.1:8100)
Gerenciador de processos gráficos e pesados de navegação (Nav2, RViz, Localização, Mission Manager)
e rotas de controle de infraestrutura no host usando a biblioteca padrão do Python 3.
"""

import os
import sys
import time
import json
import socket
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Configuração de Caminhos e Ambiente
REPO_DIR = Path(__file__).resolve().parent.parent.parent
TOKEN_FILE = REPO_DIR / "future_lab_control_center" / ".agent_token"
TB4_WS = REPO_DIR / "turtlebot4_jazzy"
DOCKER_COMPOSE_FILE = REPO_DIR / "future_lab_control_center" / "docker-compose.yml"

JAZZY_ENV_CMD = (
    "source /opt/ros/jazzy/setup.bash && "
    "source /home/future-lab/B002_Future_Lab_Bots/turtlebot4_jazzy/setup.bash && "
    "export ROS_SUPER_CLIENT=True && "
    "export ROS_DISCOVERY_SERVER='192.168.0.129:11811;' && "
    "export DISPLAY=:0 && "
    "export LIBGL_ALWAYS_SOFTWARE=1 && "
    "export QT_X11_NO_MITSHM=1"
)

# Carrega o token secreto de autenticação
def load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return "futurelab_agent_secret_token_2026_x8100"

AGENT_TOKEN = load_token()

ALLOWED_LAUNCHES = {
    "localization": f"cd {TB4_WS} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation localization.launch.py map:={TB4_WS}/maps/B002_map.yaml use_sim_time:=false autostart:=true bond_timeout:=30.0 > /tmp/nav2_localization.log 2>&1",
    "nav2": f"cd {TB4_WS} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_navigation nav2.launch.py params_file:={TB4_WS}/config/nav2_custom.yaml use_sim_time:=false autostart:=true bond_timeout:=30.0 > /tmp/nav2_stack.log 2>&1",
    "viz": f"cd {TB4_WS} && export DISPLAY=:0 && {JAZZY_ENV_CMD} && ros2 launch turtlebot4_viz view_navigation.launch.py use_sim_time:=false > /tmp/nav2_viz.log 2>&1",
    "mission_manager": f"cd {TB4_WS} && {JAZZY_ENV_CMD} && PYTHONUNBUFFERED=1 python3 -u scripts/mission_manager.py --ros-args --params-file params/waypoints.yaml > /tmp/nav2_mission_manager.log 2>&1"
}

ALLOWED_PKILLS = {
    "localization": "pkill -9 -f 'localization.launch.py' 2>/dev/null ; pkill -9 -f 'map_server' 2>/dev/null ; pkill -9 -f 'amcl' 2>/dev/null ; pkill -9 -f 'lifecycle_manager_localization' 2>/dev/null ; pkill -9 -f 'opt/ros/jazzy/lib' 2>/dev/null || true",
    "nav2": "pkill -9 -f 'nav2.launch.py' 2>/dev/null ; pkill -9 -f 'controller_server' 2>/dev/null ; pkill -9 -f 'planner_server' 2>/dev/null ; pkill -9 -f 'bt_navigator' 2>/dev/null ; pkill -9 -f 'smoother_server' 2>/dev/null ; pkill -9 -f 'behavior_server' 2>/dev/null ; pkill -9 -f 'route_server' 2>/dev/null ; pkill -9 -f 'waypoint_follower' 2>/dev/null ; pkill -9 -f 'velocity_smoother' 2>/dev/null ; pkill -9 -f 'collision_monitor' 2>/dev/null ; pkill -9 -f 'opennav_docking' 2>/dev/null ; pkill -9 -f 'lifecycle_manager_navigation' 2>/dev/null ; pkill -9 -f 'opt/ros/jazzy/lib' 2>/dev/null || true",
    "viz": "pkill -9 -f 'view_navigation.launch.py' 2>/dev/null ; pkill -9 -f 'rviz2' 2>/dev/null || true",
    "mission_manager": "pkill -9 -f 'scripts/mission_manager.py' 2>/dev/null || true"
}

PGREP_PATTERNS = {
    "localization": "localization.launch.py",
    "nav2": "nav2.launch.py",
    "viz": "rviz2",
    "mission_manager": "scripts/mission_manager.py"
}

LOG_FILES = {
    "localization": "/tmp/nav2_localization.log",
    "nav2": "/tmp/nav2_stack.log",
    "viz": "/tmp/nav2_viz.log",
    "mission_manager": "/tmp/nav2_mission_manager.log"
}

def check_port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
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
            self._send_json({"detail": "Token de agente inválido ou ausente (X-Agent-Token)."}, 401)
            return False
        return True

    def log_message(self, format, *args):
        pass  # Silencia logs de acesso padrão no console

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({
                "ok": True,
                "display": os.environ.get("DISPLAY", ":0"),
                "timestamp": time.time()
            })
            return

        if not self._verify_token():
            return

        if path == "/status":
            status = {}
            for alvo, pattern in PGREP_PATTERNS.items():
                try:
                    res = subprocess.run(f"pgrep -af '{pattern}'", shell=True, capture_output=True, text=True)
                    status[alvo] = (res.returncode == 0 and len(res.stdout.strip()) > 0)
                except Exception:
                    status[alvo] = False
            self._send_json(status)
            return

        if path.startswith("/logs/"):
            alvo = path[len("/logs/"):]
            if alvo not in LOG_FILES:
                self._send_json({"detail": f"Alvo de log '{alvo}' desconhecido."}, 404)
                return
            log_path = Path(LOG_FILES[alvo])
            lines_count = 50
            if "lines" in query:
                try: lines_count = int(query["lines"][0])
                except Exception: pass
            if not log_path.exists():
                self._send_json({"status": "success", "source": alvo, "logs": [f"Arquivo de log {log_path} ainda não foi criado."]})
                return
            try:
                res = subprocess.run(f"tail -n {lines_count} {log_path}", shell=True, capture_output=True, text=True)
                content_lines = res.stdout.splitlines() if res.returncode == 0 else []
                self._send_json({"status": "success", "source": alvo, "logs": content_lines})
            except Exception as e:
                self._send_json({"status": "error", "source": alvo, "logs": [f"Erro ao ler log: {e}"]})
            return

        if path == "/system/inventory":
            items = []
            docker_active = subprocess.run("systemctl is-active docker", shell=True, capture_output=True, text=True).stdout.strip() == "active"
            items.append({"id": 1, "name": "Docker Daemon", "host": "PC Host", "ok": docker_active, "action": "none"})

            backend_ok = False
            try:
                res = subprocess.run("docker inspect -f '{{.State.Running}}' future_lab_backend", shell=True, capture_output=True, text=True)
                backend_ok = res.stdout.strip() == "true"
            except Exception: pass
            items.append({"id": 2, "name": "Container Backend", "host": "PC Host", "ok": backend_ok, "action": "restart_backend"})

            frontend_ok = False
            try:
                res = subprocess.run("docker inspect -f '{{.State.Running}}' future_lab_frontend", shell=True, capture_output=True, text=True)
                frontend_ok = res.stdout.strip() == "true"
            except Exception: pass
            items.append({"id": 3, "name": "Container Frontend", "host": "PC Host", "ok": frontend_ok, "action": "none"})

            cobot_disc_ok = check_port_open("127.0.0.1", 11888)
            items.append({"id": 4, "name": "Discovery Server Cobot (:11888)", "host": "PC Host", "ok": cobot_disc_ok, "action": "restart_cobot_discovery"})

            items.append({"id": 5, "name": "Agente do Host (:8100)", "host": "PC Host", "ok": True, "action": "none"})

            disp_ok = bool(os.environ.get("DISPLAY"))
            items.append({"id": 6, "name": "Sessão Gráfica X11 (:0)", "host": "PC Host", "ok": disp_ok, "action": "none"})

            tb4_ping = subprocess.run("ping -c 1 -w 2 192.168.0.129", shell=True, capture_output=True).returncode == 0
            items.append({"id": 7, "name": "TurtleBot 4 Service (RPi4)", "host": "192.168.0.129", "ok": tb4_ping, "action": "restart_tb4_bringup"})

            tb4_disc_ok = check_port_open("192.168.0.129", 11811)
            items.append({"id": 8, "name": "Discovery Server TB4 (:11811)", "host": "192.168.0.129", "ok": tb4_disc_ok, "action": "none"})

            c3_ping = subprocess.run("ping -c 1 -w 2 192.168.186.2", shell=True, capture_output=True).returncode == 0 or tb4_ping
            items.append({"id": 9, "name": "Create 3 Base (usb0)", "host": "192.168.186.2", "ok": c3_ping, "action": "none"})

            nano_stream_ok = check_port_open("192.168.0.250", 8080)
            items.append({"id": 10, "name": "Jetson Nano Stream (:8080)", "host": "192.168.0.250", "ok": nano_stream_ok, "action": "none"})

            self._send_json(items)
            return

        self._send_json({"detail": "Rota GET não encontrada."}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._verify_token():
            return

        if path.startswith("/launch/"):
            alvo = path[len("/launch/"):]
            if alvo not in ALLOWED_LAUNCHES:
                self._send_json({"detail": f"Alvo '{alvo}' desconhecido. Permitidos: {list(ALLOWED_LAUNCHES.keys())}"}, 404)
                return
            try:
                subprocess.run(ALLOWED_PKILLS[alvo], shell=True, timeout=8)
                time.sleep(1.0)
                subprocess.run("xhost +local:root 2>/dev/null || xhost + 2>/dev/null || true", shell=True, timeout=3)
                cmd = ALLOWED_LAUNCHES[alvo]
                subprocess.Popen(cmd, shell=True, executable="/bin/bash", start_new_session=True)
                self._send_json({"status": "success", "message": f"Processo '{alvo}' lançado no host com sucesso!"})
            except Exception as e:
                self._send_json({"detail": f"Falha ao lançar {alvo}: {e}"}, 500)
            return

        if path.startswith("/stop/"):
            alvo = path[len("/stop/"):]
            if alvo not in ALLOWED_PKILLS:
                self._send_json({"detail": f"Alvo '{alvo}' desconhecido."}, 404)
                return
            try:
                subprocess.run(ALLOWED_PKILLS[alvo], shell=True, timeout=8)
                self._send_json({"status": "success", "message": f"Processo '{alvo}' encerrado no host."})
            except Exception as e:
                self._send_json({"detail": f"Falha ao encerrar {alvo}: {e}"}, 500)
            return

        if path == "/system/restart_backend":
            try:
                cmd = f"docker compose -f {DOCKER_COMPOSE_FILE} restart backend"
                subprocess.Popen(cmd, shell=True, executable="/bin/bash", start_new_session=True)
                self._send_json({"status": "success", "message": "Comando de reinício do backend enviado com sucesso!"})
            except Exception as e:
                self._send_json({"detail": f"Falha ao reiniciar backend: {e}"}, 500)
            return

        if path == "/system/restart_cobot_discovery":
            try:
                res = subprocess.run("systemctl --user restart future-lab-cobot-discovery", shell=True, capture_output=True, text=True, timeout=15)
                if res.returncode == 0:
                    self._send_json({"status": "success", "message": "Discovery Server do cobot (porta 11888) reiniciado com sucesso!"})
                else:
                    self._send_json({"status": "error", "message": f"Erro systemctl: {res.stderr.strip() or res.stdout.strip()}"})
            except Exception as e:
                self._send_json({"detail": f"Falha ao reiniciar discovery server do cobot: {e}"}, 500)
            return

        if path == "/robot/restart_bringup":
            try:
                cmd = "ssh -o ConnectTimeout=5 ubuntu@192.168.0.129 'echo turtlebot4 | sudo -S systemctl restart turtlebot4.service'"
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=45)
                if res.returncode == 0:
                    self._send_json({"status": "success", "message": "Serviço turtlebot4.service reiniciado no Raspberry Pi 4 com sucesso!"})
                else:
                    self._send_json({"status": "error", "message": f"Falha SSH: {res.stderr.strip() or res.stdout.strip()}"})
            except Exception as e:
                self._send_json({"detail": f"Erro ao reiniciar bringup do robô: {e}"}, 500)
            return

        if path == "/robot/start_oakd":
            try:
                cmd = "ssh -o ConnectTimeout=5 ubuntu@192.168.0.129 'source /etc/turtlebot4/setup.bash && ros2 service call /oakd/start_camera std_srvs/srv/Trigger {}'"
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                if res.returncode == 0:
                    self._send_json({"status": "success", "message": "Câmera OAK-D ativada via ROS 2 Service!"})
                else:
                    self._send_json({"status": "error", "message": f"Falha SSH: {res.stderr.strip() or res.stdout.strip()}"})
            except Exception as e:
                self._send_json({"detail": f"Erro ao iniciar câmera OAK-D: {e}"}, 500)
            return

        self._send_json({"detail": "Rota POST não encontrada."}, 404)

if __name__ == "__main__":
    server = ThreadedHTTPServer(("127.0.0.1", 8100), AgentRequestHandler)
    print("[INFO] Future Lab Host Agent rodando em http://127.0.0.1:8100...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
