#!/usr/bin/env python3
"""Envia um único /start_delivery mantendo a classe fresca em paralelo."""

from __future__ import annotations

import argparse
import json
import sys
import time

import rclpy
from std_msgs.msg import String
from std_srvs.srv import Trigger


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--value", required=True, choices=("tin_valid_blue", "tin_valid_red")
    )
    parser.add_argument("--discovery-timeout", type=float, default=15.0)
    parser.add_argument("--response-timeout", type=float, default=15.0)
    args = parser.parse_args()

    rclpy.init()
    # Mantém o nome do requester que comprovadamente alcança o serviço neste
    # grafo Fast DDS, mas reúne publisher e client no mesmo participante.
    node = rclpy.create_node("_ros2cli_requester_std_srvs_Trigger")
    try:
        publisher = node.create_publisher(String, "/product_class", 10)
        client = node.create_client(Trigger, "/start_delivery")
        message = String(data=args.value)

        discovery_deadline = time.monotonic() + args.discovery_timeout
        service_ready = False
        subscribers = 0
        while time.monotonic() < discovery_deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            subscribers = int(publisher.get_subscription_count())
            service_ready = client.service_is_ready()
            if subscribers > 0:
                publisher.publish(message)
            if subscribers > 0 and service_ready:
                break

        if subscribers < 1 or not service_ready:
            emit({
                "request_sent": False,
                "subscriber_count": subscribers,
                "service_ready": service_ready,
                "error": "Descoberta de /product_class e /start_delivery incompleta.",
            })
            return 3

        # Preenche o cache da rotina e garante que a amostra já seja fresca
        # quando o callback do serviço iniciar a missão.
        for _ in range(5):
            publisher.publish(message)
            rclpy.spin_once(node, timeout_sec=0.05)

        future = client.call_async(Trigger.Request())
        published_count = 5
        response_deadline = time.monotonic() + args.response_timeout
        while time.monotonic() < response_deadline:
            publisher.publish(message)
            published_count += 1
            rclpy.spin_once(node, timeout_sec=0.05)
            if future.done():
                response = future.result()
                emit({
                    "request_sent": True,
                    "responded": response is not None,
                    "success": bool(response.success) if response else False,
                    "message": response.message if response else "",
                    "subscriber_count": subscribers,
                    "published_count": published_count,
                })
                return 0 if response is not None else 5

        emit({
            "request_sent": True,
            "responded": False,
            "subscriber_count": subscribers,
            "published_count": published_count,
            "error": "Resposta do serviço não recebida; verificar evidência no log.",
        })
        return 5
    except Exception as exc:
        emit({"request_sent": False, "error": f"{type(exc).__name__}: {exc}"})
        return 6
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
