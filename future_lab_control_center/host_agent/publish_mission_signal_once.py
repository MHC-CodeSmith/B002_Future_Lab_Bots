#!/usr/bin/env python3
"""Publica exatamente um tipo de sinal de missão no grafo ROS do host."""

from __future__ import annotations

import argparse
import json
import sys
import time

import rclpy
from std_msgs.msg import Bool, String


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--signal", required=True, choices=("product_class", "item_released")
    )
    parser.add_argument("--value", default="")
    parser.add_argument("--discovery-timeout", type=float, default=5.0)
    args = parser.parse_args()

    if args.signal == "product_class" and args.value not in {
        "tin_valid_blue", "tin_valid_red"
    }:
        emit({"published": False, "error": "Classe de produto não permitida."})
        return 2

    rclpy.init()
    node = rclpy.create_node("_future_lab_mission_signal_publisher")
    try:
        if args.signal == "product_class":
            topic = "/product_class"
            publisher = node.create_publisher(String, topic, 10)
            message = String(data=args.value)
        else:
            topic = "/item_released_on_tb4"
            publisher = node.create_publisher(Bool, topic, 10)
            message = Bool(data=True)

        deadline = time.monotonic() + args.discovery_timeout
        subscribers = 0
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            subscribers = int(publisher.get_subscription_count())
            if subscribers > 0:
                break
        if subscribers < 1:
            emit({
                "published": False,
                "topic": topic,
                "subscriber_count": 0,
                "error": "Nenhum subscriber ROS descoberto para o tópico.",
            })
            return 3

        for _ in range(10):
            publisher.publish(message)
            rclpy.spin_once(node, timeout_sec=0.1)

        emit({
            "published": True,
            "topic": topic,
            "value": args.value if args.signal == "product_class" else True,
            "subscriber_count": subscribers,
            "published_count": 10,
        })
        return 0
    except Exception as exc:
        emit({"published": False, "error": f"{type(exc).__name__}: {exc}"})
        return 4
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
