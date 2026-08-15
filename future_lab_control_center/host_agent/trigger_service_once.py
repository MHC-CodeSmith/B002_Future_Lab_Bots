#!/usr/bin/env python3
"""Executa exatamente uma chamada std_srvs/Trigger no grafo ROS do host."""

from __future__ import annotations

import argparse
import json
import sys

import rclpy
from std_srvs.srv import Trigger


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--discovery-timeout", type=float, default=20.0)
    parser.add_argument("--response-timeout", type=float, default=20.0)
    args = parser.parse_args()

    if not args.service.startswith("/"):
        emit({"responded": False, "error": "Nome de serviço inválido."})
        return 2
    if args.discovery_timeout <= 0 or args.response_timeout <= 0:
        emit({"responded": False, "error": "Timeouts precisam ser positivos."})
        return 2

    rclpy.init()
    # No grafo Fast DDS atual, a mesma requisição só recebeu resposta quando
    # reproduziu também o nome usado pelo requester oficial do ros2service.
    # O agente do host serializa execuções para impedir colisões desse nome.
    node = rclpy.create_node("_ros2cli_requester_std_srvs_Trigger")
    try:
        client = node.create_client(Trigger, args.service)
        if not client.service_is_ready():
            # Também replica o requester oficial sem timeout interno. O
            # subprocesso pai é o watchdog e nunca repete a chamada.
            client.wait_for_service()

        future = client.call_async(Trigger.Request())
        # Igual ao requester oficial de ``ros2 service call``. Com Fast DDS
        # Discovery Server, o spin temporizado não processou a resposta mesmo
        # quando o CLI oficial a recebeu. O processo pai aplica o prazo total
        # e encerra este helper se necessário; a requisição nunca é repetida.
        rclpy.spin_until_future_complete(node, future)

        response = future.result()
        if response is None:
            emit({
                "responded": False,
                "service": args.service,
                "stage": "response",
                "request_sent": True,
                "error": "Future concluído sem resposta.",
            })
            return 5

        emit({
            "responded": True,
            "service": args.service,
            "success": bool(response.success),
            "message": response.message or "",
        })
        return 0
    except Exception as exc:
        emit({
            "responded": False,
            "service": args.service,
            "error": f"{type(exc).__name__}: {exc}",
        })
        return 6
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
