import types
import unittest
from unittest.mock import patch

from backend.mission_readiness import mission_readiness
from backend.mission_signal_evidence import is_new_evidence, latest_matching_timestamp
from backend.ros2_nodes import cobot_node


def ready_checks(*, undocked):
    return {
        "create3_alive": True,
        "create3_dock_action": True,
        "create3_undock_action": True,
        "undocked": undocked,
        "odom": True,
        "scan": False,
        "map": True,
        "amcl_pose": False,
        "navigate_to_pose": True,
        "global_costmap": True,
        "start_delivery": True,
        "stop_mission": True,
    }


class MissionReadinessTest(unittest.TestCase):
    def test_docked_mission_does_not_require_sleeping_lidar_or_fresh_amcl(self):
        status = mission_readiness(ready_checks(undocked=False))
        self.assertTrue(status["ready"])
        self.assertEqual("docked", status["start_mode"])
        self.assertNotIn("scan", status["required"])
        self.assertNotIn("amcl_pose", status["required"])

    def test_undocked_mission_requires_fresh_navigation_inputs(self):
        status = mission_readiness(ready_checks(undocked=True))
        self.assertFalse(status["ready"])
        self.assertEqual("undocked", status["start_mode"])
        self.assertEqual(["scan", "amcl_pose"], status["missing"])

    def test_missing_mission_service_is_reported(self):
        checks = ready_checks(undocked=False)
        checks["start_delivery"] = False
        status = mission_readiness(checks)
        self.assertFalse(status["ready"])
        self.assertIn("start_delivery", status["missing"])


class MissionSignalEvidenceTest(unittest.TestCase):
    def test_selects_latest_matching_ros_timestamp(self):
        marker = "Tópico /product_class recebido"
        lines = [
            "[INFO] [10.1] [delivery_routine]: Tópico /product_class recebido: blue",
            "[WARN] [11.5] [other]: outra mensagem",
            "[INFO] [12.3] [delivery_routine]: Tópico /product_class recebido: red",
        ]
        self.assertEqual(12.3, latest_matching_timestamp(lines, marker))

    def test_old_matching_line_is_not_new_evidence(self):
        self.assertFalse(is_new_evidence(12.3, 12.3))
        self.assertFalse(is_new_evidence(12.2, 12.3))
        self.assertTrue(is_new_evidence(12.4, 12.3))

    def test_missing_marker_is_not_evidence(self):
        self.assertIsNone(latest_matching_timestamp(["sem marker"], "esperado"))
        self.assertFalse(is_new_evidence(None, None))


class SimulatedSignalPublisherTest(unittest.TestCase):
    def test_product_class_reports_publication(self):
        published = []
        node = types.SimpleNamespace(
            product_class_pub=types.SimpleNamespace(
                publish=lambda msg: published.append(msg.data)
            )
        )
        with patch.object(cobot_node, "String", type("String", (), {})):
            self.assertTrue(cobot_node.CobotNode.publish_product_class(node, "tin_valid_blue"))
        self.assertEqual(["tin_valid_blue"] * 3, published)

    def test_product_class_fails_when_publisher_is_missing(self):
        node = types.SimpleNamespace(product_class_pub=None)
        self.assertFalse(cobot_node.CobotNode.publish_product_class(node, "tin_valid_blue"))

    def test_item_release_reports_publication(self):
        published = []
        node = types.SimpleNamespace(
            item_released_pub=types.SimpleNamespace(
                publish=lambda msg: published.append(msg.data)
            )
        )
        with patch.object(cobot_node, "Bool", type("Bool", (), {})):
            self.assertTrue(cobot_node.CobotNode.publish_item_released(node))
        self.assertEqual([True] * 5, published)


if __name__ == "__main__":
    unittest.main()
