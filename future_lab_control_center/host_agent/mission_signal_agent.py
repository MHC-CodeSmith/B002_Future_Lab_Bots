#!/usr/bin/env python3
"""Ponte HTTP mínima para sinais simulados do cobot (127.0.0.1:8101)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent as main_agent
from backend.mission_signal_evidence import is_new_evidence, latest_matching_timestamp


HELPER = Path(__file__).resolve().parent / "publish_mission_signal_once.py"
DELIVERY_HELPER = (
    Path(__file__).resolve().parent / "start_delivery_with_class_once.py"
)
MISSION_LOG = Path(main_agent.LOG_FILES["mission_manager"])
PUBLISH_LOCK = threading.Lock()
DELIVERY_START_LOCK = threading.Lock()


def _latest_marker_timestamp(marker: str) -> float | None:
    try:
        lines = MISSION_LOG.read_text(errors="replace").splitlines()[-1000:]
    except OSError:
        lines = []
    return latest_matching_timestamp(lines, marker)


def publish_and_confirm(signal: str, value: str = "") -> tuple[dict, int]:
    allowed = {
        "product_class": {"tin_valid_blue", "tin_valid_red"},
        "item_released": {""},
    }
    if signal not in allowed or value not in allowed[signal]:
        return {"detail": "Sinal ou valor não permitido."}, 422

    marker = (
        f"Tópico /product_class recebido no TurtleBot 4: '{value}'"
        if signal == "product_class"
        else "Confirmação /item_released_on_tb4 recebida"
    )
    previous = _latest_marker_timestamp(marker)
    command = (
        f"{main_agent.JAZZY_ENV_CMD} && exec python3 '{HELPER}' "
        '--signal "$1" --value "$2" --discovery-timeout 5.0'
    )
    try:
        with PUBLISH_LOCK:
            completed = subprocess.run(
                ["/bin/bash", "-lc", command, "mission-signal", signal, value],
                cwd=str(main_agent.REPO_DIR),
                capture_output=True,
                text=True,
                timeout=15.0,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return {"detail": "Timeout ao publicar o sinal ROS no host."}, 504
    except OSError as exc:
        return {"detail": f"Falha ao executar publisher do host: {exc}"}, 500

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
        return {
            "detail": "Publisher do host terminou sem resposta JSON mensurável.",
            "diagnostic": (completed.stderr or completed.stdout).strip()[-1000:],
        }, 500
    if completed.returncode != 0 or not result.get("published"):
        result["detail"] = result.get("error", "Sinal ROS não foi publicado.")
        return result, 503

    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        observed = _latest_marker_timestamp(marker)
        if is_new_evidence(observed, previous):
            result.update({
                "received_by_mission": True,
                "received_log_timestamp": observed,
                "confirmation": marker,
            })
            return result, 200
        time.sleep(0.05)

    result.update({
        "received_by_mission": False,
        "detail": "Sinal publicado, mas não confirmado no log da delivery_routine.",
    })
    return result, 504


def _stop_exact_process(process: subprocess.Popen) -> None:
    """Recolhe somente o helper iniciado por esta requisição."""
    if process.poll() is not None:
        process.communicate()
        return
    process.terminate()
    try:
        process.communicate(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=2.0)


def start_delivery_and_confirm(value: str) -> tuple[dict, int]:
    """Publica uma classe fresca, chama /start_delivery e prova o destino no log."""
    targets = {
        "tin_valid_blue": "delivery_blue",
        "tin_valid_red": "delivery_red",
    }
    target = targets.get(value)
    if target is None:
        return {"detail": "Classe de delivery não permitida."}, 422

    with DELIVERY_START_LOCK:
        class_marker = (
            f"Tópico /product_class recebido no TurtleBot 4: '{value}'"
        )
        trigger_marker = "Trigger recebido: delivery"
        target_marker = (
            "Classe válida e fresca confirmada; destino desta missão: "
            f"'{target}'"
        )
        previous_class = _latest_marker_timestamp(class_marker)
        previous_trigger = _latest_marker_timestamp(trigger_marker)
        previous_target = _latest_marker_timestamp(target_marker)
        command = (
            f"{main_agent.JAZZY_ENV_CMD} && exec python3 '{DELIVERY_HELPER}' "
            f"--value '{value}' --discovery-timeout 15.0 "
            "--response-timeout 15.0"
        )
        try:
            process = subprocess.Popen(
                ["/bin/bash", "-lc", command],
                cwd=str(main_agent.REPO_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            return {
                "detail": f"Falha ao iniciar requester de /start_delivery: {exc}",
            }, 500

        observed_class = None
        observed_trigger = None
        observed_target = None
        deadline = time.monotonic() + 20.0
        try:
            while time.monotonic() < deadline:
                observed_class = _latest_marker_timestamp(class_marker)
                observed_trigger = _latest_marker_timestamp(trigger_marker)
                observed_target = _latest_marker_timestamp(target_marker)
                if (
                    is_new_evidence(observed_class, previous_class)
                    and
                    is_new_evidence(observed_trigger, previous_trigger)
                    and is_new_evidence(observed_target, previous_target)
                ):
                    return {
                        "started": True,
                        "product_class": value,
                        "target": target,
                        "class_log_timestamp": observed_class,
                        "trigger_log_timestamp": observed_trigger,
                        "target_log_timestamp": observed_target,
                        "confirmation": target_marker,
                    }, 200
                if process.poll() is not None:
                    # Dá tempo para o flush do log depois de o requester sair.
                    time.sleep(0.2)
                time.sleep(0.05)

            trigger_was_received = is_new_evidence(
                observed_trigger, previous_trigger
            )
            return {
                "started": False,
                "request_state": (
                    "trigger_received_target_unconfirmed"
                    if trigger_was_received
                    else "trigger_unconfirmed"
                ),
                "detail": (
                    "/start_delivery chegou ao Manager, mas o destino não foi "
                    "confirmado; não repita automaticamente."
                    if trigger_was_received
                    else "/start_delivery não foi confirmado no log do Manager."
                ),
            }, 504
        finally:
            _stop_exact_process(process)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass

    def _send(self, data: dict, code: int):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send({"ok": True, "service": "mission_signal_agent"}, 200)
        else:
            self._send({"detail": "Rota não encontrada."}, 404)

    def do_POST(self):
        if self.headers.get("X-Agent-Token", "").strip() != main_agent.AGENT_TOKEN:
            self._send({"detail": "Token inválido ou ausente."}, 401)
            return
        if self.path not in {"/publish", "/start_delivery"}:
            self._send({"detail": "Rota não encontrada."}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError("Corpo JSON ausente ou grande demais.")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            signal = str(body.get("signal", ""))
            value = str(body.get("value", ""))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send({"detail": str(exc)}, 422)
            return
        if self.path == "/start_delivery":
            result, code = start_delivery_and_confirm(value)
        else:
            result, code = publish_and_confirm(signal, value)
        self._send(result, code)


if __name__ == "__main__":
    server = ThreadedHTTPServer(("127.0.0.1", 8101), Handler)
    print("[INFO] Mission Signal Agent em http://127.0.0.1:8101", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
