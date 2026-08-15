#!/usr/bin/env python3
"""Publica /initialpose no host e so retorna sucesso apos nova /amcl_pose."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSProfile, QoSReliabilityPolicy


def stamp_ns(stamp) -> int:
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


SETTING_POSE_RE = re.compile(
    r"Setting pose \([^)]*\):\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)"
)


class InitialPoseOnce(Node):
    def __init__(self):
        # Evita reaproveitamento temporario do mesmo nome/participant DDS em
        # chamadas consecutivas do helper.
        super().__init__(f"future_lab_initial_pose_once_{os.getpid()}")
        initial_pose_qos = QoSProfile(
            depth=10,
            # Igual ao publisher do RViz. Um publisher RELIABLE atende tanto
            # o AMCL BEST_EFFORT quanto ferramentas/subscribers RELIABLE.
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        amcl_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.publisher = self.create_publisher(
            PoseWithCovarianceStamped, "/initialpose", initial_pose_qos
        )
        self.subscription = self.create_subscription(
            PoseWithCovarianceStamped, "/amcl_pose", self._amcl_callback, amcl_qos
        )
        self.request_stamp_ns = 0
        self.confirmed = None

    def _amcl_callback(self, msg):
        if not self.request_stamp_ns or stamp_ns(msg.header.stamp) < self.request_stamp_ns:
            return
        pose = msg.pose.pose
        q = pose.orientation
        yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )
        cov = list(msg.pose.covariance)
        self.confirmed = {
            "pose": {
                "x": round(float(pose.position.x), 4),
                "y": round(float(pose.position.y), 4),
                "yaw": round(float(yaw), 4),
            },
            "covariance": {
                "x": round(float(cov[0]), 5),
                "y": round(float(cov[7]), 5),
                "yaw": round(float(cov[35]), 5),
            },
            "stamp_ns": stamp_ns(msg.header.stamp),
        }

    @staticmethod
    def _log_confirmation(log_path: Path, offset: int, x: float, y: float, yaw: float):
        try:
            with log_path.open("rb") as handle:
                if log_path.stat().st_size < offset:
                    offset = 0
                handle.seek(offset)
                text = handle.read().decode("utf-8", "replace")
        except OSError:
            return None
        for match in SETTING_POSE_RE.finditer(text):
            observed = tuple(float(value) for value in match.groups())
            expected = (x, y, yaw)
            if all(math.isclose(a, b, abs_tol=0.002) for a, b in zip(observed, expected)):
                return {
                    "pose": {"x": observed[0], "y": observed[1], "yaw": observed[2]},
                    "confirmation_source": "amcl_log_setting_pose",
                }
        return None

    def publish_and_confirm(
        self, x: float, y: float, yaw: float, timeout: float, amcl_log: Path
    ) -> dict:
        # Um unico prazo total: em Discovery Server carregado, um participant
        # novo pode levar varios segundos para enxergar o subscriber do AMCL.
        overall_deadline = time.monotonic() + timeout
        discovery_deadline = overall_deadline
        while self.count_subscribers("/initialpose") < 1 and time.monotonic() < discovery_deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        subscribers = self.count_subscribers("/initialpose")
        if subscribers < 1:
            return {"ok": False, "error": "AMCL não foi encontrado como subscriber de /initialpose."}

        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = "map"
        msg.pose.pose.position.x = x
        msg.pose.pose.position.y = y
        half_yaw = yaw * 0.5
        msg.pose.pose.orientation.z = math.sin(half_yaw)
        msg.pose.pose.orientation.w = math.cos(half_yaw)
        msg.pose.covariance[0] = 0.25
        msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.06853891945200942

        try:
            log_offset = amcl_log.stat().st_size
        except OSError:
            log_offset = 0

        request_stamp = self.get_clock().now().to_msg()
        self.request_stamp_ns = stamp_ns(request_stamp)

        confirm_deadline = overall_deadline
        next_publish = 0.0
        log_confirmation = None
        log_grace_deadline = None
        while self.confirmed is None and time.monotonic() < confirm_deadline:
            now = time.monotonic()
            if now >= next_publish:
                msg.header.stamp = self.get_clock().now().to_msg()
                self.publisher.publish(msg)
                next_publish = now + 0.25
            rclpy.spin_once(self, timeout_sec=0.1)
            if log_confirmation is None:
                log_confirmation = self._log_confirmation(
                    amcl_log, log_offset, x, y, yaw
                )
                if log_confirmation is not None:
                    # Com laser ativo, da uma janela curta para capturar a
                    # /amcl_pose (pose + covariancia) em vez de so o log.
                    log_grace_deadline = time.monotonic() + 2.0
            if (
                log_confirmation is not None
                and log_grace_deadline is not None
                and time.monotonic() >= log_grace_deadline
            ):
                return {
                    "ok": True,
                    "subscribers": subscribers,
                    **log_confirmation,
                }

        if self.confirmed is None:
            if log_confirmation is not None:
                return {
                    "ok": True,
                    "subscribers": subscribers,
                    **log_confirmation,
                }
            return {
                "ok": False,
                "error": f"Pose publicada para {subscribers} subscriber(s), mas /amcl_pose não confirmou em {timeout:.1f}s.",
            }
        return {
            "ok": True,
            "subscribers": subscribers,
            "confirmation_source": "amcl_pose_topic",
            **self.confirmed,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--yaw", type=float, required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--amcl-log", type=Path, default=Path("/tmp/nav2_localization.log")
    )
    args = parser.parse_args()
    if not all(math.isfinite(value) for value in (args.x, args.y, args.yaw)):
        print(json.dumps({"ok": False, "error": "X, Y e yaw precisam ser finitos."}))
        return 2

    rclpy.init()
    node = InitialPoseOnce()
    try:
        result = node.publish_and_confirm(
            args.x, args.y, args.yaw, args.timeout, args.amcl_log
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
