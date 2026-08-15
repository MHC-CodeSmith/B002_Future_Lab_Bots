import threading
import time
import types
import unittest
from unittest.mock import patch

from builtin_interfaces.msg import Time

from backend.ros2_nodes import turtlebot_node as module


class FakeStamp:
    def to_msg(self):
        return Time(sec=1, nanosec=0)


class FakeClock:
    def now(self):
        return FakeStamp()


def fake_pose_node(subscribers=1, acknowledge=False):
    node = types.SimpleNamespace()
    node._initial_pose_ack = threading.Event()
    node._initial_pose_request_started = 0.0
    node.amcl_pose = None
    node.count_subscribers = lambda _topic: subscribers
    node.get_clock = lambda: FakeClock()

    class Publisher:
        def publish(self, _msg):
            if acknowledge:
                node.amcl_pose = {"x": 1.0, "y": 2.0, "yaw": 0.5}
                node._initial_pose_ack.set()

    node.initialpose_pub = Publisher()
    return node


class InitialPoseConfirmationTest(unittest.TestCase):
    def test_fails_when_amcl_has_no_subscription(self):
        node = fake_pose_node(subscribers=0)
        ok, message, observed = module.TurtleBotNode.publish_initial_pose(
            node, 1.0, 2.0, 0.5, confirm_sec=0.01
        )
        self.assertFalse(ok)
        self.assertIsNone(observed)
        self.assertIn("não está inscrito", message)

    def test_success_requires_amcl_acknowledgement(self):
        node = fake_pose_node(acknowledge=True)
        with patch.object(module.time, "sleep", return_value=None):
            ok, message, observed = module.TurtleBotNode.publish_initial_pose(
                node, 1.0, 2.0, 0.5, confirm_sec=0.01
            )
        self.assertTrue(ok, message)
        self.assertEqual({"x": 1.0, "y": 2.0, "yaw": 0.5}, observed)

    def test_publish_without_acknowledgement_is_not_success(self):
        node = fake_pose_node(acknowledge=False)
        with patch.object(module.time, "sleep", return_value=None):
            ok, message, observed = module.TurtleBotNode.publish_initial_pose(
                node, 1.0, 2.0, 0.5, confirm_sec=0.01
            )
        self.assertFalse(ok)
        self.assertIsNone(observed)
        self.assertIn("nenhuma nova /amcl_pose", message)

    def test_external_measurement_keeps_real_covariance(self):
        node = types.SimpleNamespace(
            amcl_pose=None,
            amcl_cov=None,
            last_amcl_time=0.0,
            amcl_source=None,
            amcl_initialized=False,
        )
        ok = module.TurtleBotNode.record_external_amcl_measurement(
            node,
            {"x": 1.0, "y": 2.0, "yaw": 0.5},
            {"x": 0.15, "y": 0.23, "yaw": 0.06},
            "host_test",
        )
        self.assertTrue(ok)
        self.assertEqual({"x": 0.15, "y": 0.23, "yaw": 0.06}, node.amcl_cov)
        self.assertEqual("host_test", node.amcl_source)
        self.assertTrue(node.amcl_initialized)

    def test_external_measurement_rejects_nonfinite_value(self):
        node = types.SimpleNamespace(
            amcl_pose=None,
            amcl_cov=None,
            last_amcl_time=0.0,
            amcl_source=None,
            amcl_initialized=False,
        )
        ok = module.TurtleBotNode.record_external_amcl_measurement(
            node,
            {"x": float("nan"), "y": 2.0, "yaw": 0.5},
            None,
            "host_test",
        )
        self.assertFalse(ok)

    def test_initialized_pose_is_distinct_from_fresh_message(self):
        node = types.SimpleNamespace(
            amcl_pose={"x": 1.0, "y": 2.0, "yaw": 0.5},
            amcl_cov={"x": 0.15, "y": 0.23, "yaw": 0.06},
            last_amcl_time=time.time() - module.AMCL_TTL - 1.0,
            amcl_source="host_test",
            amcl_initialized=True,
            init_errors=[],
        )
        status = module.TurtleBotNode.get_amcl(node)
        self.assertTrue(status["initialized"])
        self.assertFalse(status["amcl_ok"])
        self.assertIn("ultima leitura", status["motivo"])


class ScanFreshnessTest(unittest.TestCase):
    def test_publisher_name_without_message_is_not_fresh(self):
        node = types.SimpleNamespace(
            last_scan_time=0.0,
            last_scan_frame=None,
            count_publishers=lambda _topic: 1,
        )
        status = module.TurtleBotNode.get_scan_status(node)
        self.assertFalse(status["fresh"])
        self.assertEqual(1, status["publisher_count"])
        self.assertIn("nenhuma mensagem", status["reason"])

    def test_recent_message_is_fresh(self):
        node = types.SimpleNamespace(
            last_scan_time=time.time(),
            last_scan_frame="rplidar_link",
            count_publishers=lambda _topic: 1,
        )
        status = module.TurtleBotNode.get_scan_status(node)
        self.assertTrue(status["fresh"])
        self.assertEqual("rplidar_link", status["frame_id"])


if __name__ == "__main__":
    unittest.main()
