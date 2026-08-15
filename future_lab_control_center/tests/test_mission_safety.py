import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from action_msgs.msg import GoalStatus
from std_msgs.msg import Bool


SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "turtlebot4_jazzy" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import delivery_routine as delivery_module  # noqa: E402
import mission_base as mission_module  # noqa: E402


class ImmediateFuture:
    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result

    def add_done_callback(self, callback):
        callback(self)


class FakeLogger:
    def __init__(self):
        self.messages = []

    def _record(self, level, message):
        self.messages.append((level, message))

    def info(self, message):
        self._record("info", message)

    def warn(self, message):
        self._record("warn", message)

    def error(self, message):
        self._record("error", message)


class FakeGoalHandle:
    def __init__(self, accepted, status):
        self.accepted = accepted
        self.status = status

    def get_result_async(self):
        return ImmediateFuture(types.SimpleNamespace(status=self.status))


class FakeActionClient:
    def __init__(self, available=True, accepted=True, status=GoalStatus.STATUS_SUCCEEDED):
        self.available = available
        self.accepted = accepted
        self.status = status
        self.sent = 0

    def wait_for_server(self, timeout_sec):
        return self.available

    def send_goal_async(self, _goal):
        self.sent += 1
        return ImmediateFuture(FakeGoalHandle(self.accepted, self.status))


def fake_undock_node(docked, client):
    node = types.SimpleNamespace(
        _is_docked=docked,
        _last_dock_status_monotonic=(
            time.monotonic() if docked is not None else None
        ),
        dock_status_max_age_s=3.0,
        undock_client=client,
        post_undock_stabilize_s=8.0,
        _nav_not_before_monotonic=0.0,
        clear_count=0,
        logger=FakeLogger(),
    )
    node.get_logger = lambda: node.logger

    def clear_costmaps():
        node.clear_count += 1
        return True

    node.clear_costmaps = clear_costmaps
    return node


class DeliveryClassificationTest(unittest.TestCase):
    def test_known_classes_have_explicit_destinations(self):
        for value in ("red", "vermelho", "tin_valid_red", "tin_valid_red_square"):
            self.assertEqual("delivery_red", delivery_module.delivery_target_for_class(value))
        for value in ("blue", "azul", "tin_valid_blue", "tin_valid_blue_square"):
            self.assertEqual("delivery_blue", delivery_module.delivery_target_for_class(value))

    def test_unknown_or_invalid_class_never_defaults_to_red(self):
        for value in ("", "unknown", "tin_invalid", "green", "infrared"):
            self.assertIsNone(delivery_module.delivery_target_for_class(value))

    def test_classification_must_be_recent(self):
        self.assertTrue(delivery_module.classification_is_fresh(98.0, 100.0, 5.0))
        self.assertFalse(delivery_module.classification_is_fresh(90.0, 100.0, 5.0))
        self.assertFalse(delivery_module.classification_is_fresh(None, 100.0, 5.0))
        self.assertFalse(delivery_module.classification_is_fresh(101.0, 100.0, 5.0))

    def test_item_release_is_ignored_outside_handoff_window(self):
        node = types.SimpleNamespace(
            _waiting_for_item_release=False,
            _item_released_monotonic=None,
            get_logger=lambda: FakeLogger(),
        )
        delivery_module.DeliveryRoutine._on_item_released(node, Bool(data=True))
        self.assertIsNone(node._item_released_monotonic)

        node._waiting_for_item_release = True
        with patch.object(delivery_module.time, "monotonic", return_value=123.0):
            delivery_module.DeliveryRoutine._on_item_released(node, Bool(data=True))
        self.assertEqual(123.0, node._item_released_monotonic)

    def test_start_without_class_does_not_call_undock(self):
        timers = []
        node = types.SimpleNamespace(
            vision_timeout=10.0,
            _cb_group=object(),
            _mission_delivery_target="old",
            _waiting_for_item_release=True,
            _item_released_monotonic=1.0,
            logger=FakeLogger(),
            undock_calls=0,
        )
        node.get_logger = lambda: node.logger
        node.begin_mission = lambda *_args, **_kwargs: None
        node._cancel_delivery_timers = lambda: None
        node._fresh_delivery_target = lambda: None
        node._start_with_target = lambda _target: setattr(
            node, "undock_calls", node.undock_calls + 1
        )
        node.create_timer = lambda _period, callback, **_kwargs: timers.append(callback)

        delivery_module.DeliveryRoutine.start(node)

        self.assertEqual(0, node.undock_calls)
        self.assertEqual(1, len(timers))

    def test_pickup_waits_for_release_before_delivery(self):
        callbacks = []
        published = []
        delivered = []
        node = types.SimpleNamespace(
            _mission_delivery_target="delivery_blue",
            _waiting_for_item_release=False,
            _item_released_monotonic=None,
            handoff_timeout_s=90.0,
            pickup_announce_period_s=0.5,
            _cb_group=object(),
            _handoff_timer=None,
            logger=FakeLogger(),
            _pickup_pub=types.SimpleNamespace(
                publish=lambda msg: published.append(bool(msg.data))
            ),
        )
        node.get_logger = lambda: node.logger
        node.create_timer = lambda _period, callback, **_kwargs: callbacks.append(callback)
        node._cancel_timer = lambda attribute: setattr(node, attribute, None)
        node.finish_mission = lambda *_args: self.fail("handoff não deveria falhar")
        node._go_deliver = delivered.append

        delivery_module.DeliveryRoutine._wait_for_item_release(node)
        self.assertEqual([], delivered)
        self.assertTrue(node._waiting_for_item_release)

        callbacks[0]()
        self.assertEqual([True], published)
        self.assertEqual([], delivered)

        node._item_released_monotonic = time.monotonic()
        callbacks[0]()
        self.assertEqual(["delivery_blue"], delivered)

    def test_cancel_timer_never_destroys_entity_during_callback(self):
        timer = types.SimpleNamespace(cancelled=False)
        timer.cancel = lambda: setattr(timer, "cancelled", True)
        destroyed = []
        node = types.SimpleNamespace(
            _classification_timer=timer,
            destroy_timer=destroyed.append,
        )

        delivery_module.DeliveryRoutine._cancel_timer(
            node, "_classification_timer"
        )

        self.assertTrue(timer.cancelled)
        self.assertIsNone(node._classification_timer)
        self.assertEqual([], destroyed)


class UndockSafetyTest(unittest.TestCase):
    def call(self, node):
        results = []
        mission_module.MissionBase.undock(node, results.append)
        return results

    def test_unknown_dock_state_fails_without_sending_goal(self):
        client = FakeActionClient()
        node = fake_undock_node(None, client)
        self.assertEqual([False], self.call(node))
        self.assertEqual(0, client.sent)

    def test_unavailable_undock_server_is_failure(self):
        client = FakeActionClient(available=False)
        node = fake_undock_node(True, client)
        self.assertEqual([False], self.call(node))
        self.assertEqual(0, client.sent)

    def test_stale_dock_status_is_failure(self):
        client = FakeActionClient()
        node = fake_undock_node(True, client)
        node._last_dock_status_monotonic = time.monotonic() - 10.0
        self.assertEqual([False], self.call(node))
        self.assertEqual(0, client.sent)

    def test_rejected_undock_is_failure(self):
        client = FakeActionClient(accepted=False)
        node = fake_undock_node(True, client)
        self.assertEqual([False], self.call(node))

    def test_aborted_undock_is_failure(self):
        client = FakeActionClient(status=GoalStatus.STATUS_ABORTED)
        node = fake_undock_node(True, client)
        self.assertEqual([False], self.call(node))
        self.assertEqual(0, node.clear_count)

    def test_success_is_measured_before_continuing(self):
        client = FakeActionClient(status=GoalStatus.STATUS_SUCCEEDED)
        node = fake_undock_node(True, client)
        before = time.monotonic()
        self.assertEqual([True], self.call(node))
        self.assertFalse(node._is_docked)
        self.assertEqual(1, node.clear_count)
        self.assertGreaterEqual(node._nav_not_before_monotonic, before + 7.9)


class NavigationFreshnessTest(unittest.TestCase):
    def test_receipt_freshness_has_no_unmeasured_default(self):
        self.assertFalse(mission_module.receipt_is_fresh(None, 10.0, 3.0))
        self.assertTrue(mission_module.receipt_is_fresh(8.0, 10.0, 3.0))
        self.assertFalse(mission_module.receipt_is_fresh(6.0, 10.0, 3.0))
        self.assertFalse(mission_module.receipt_is_fresh(11.0, 10.0, 3.0))

    def test_costmap_cleanup_has_no_shell_or_forbidden_discovery_override(self):
        source = (SCRIPTS_DIR / "mission_base.py").read_text(encoding="utf-8")
        self.assertNotIn("ROS_AUTOMATIC_DISCOVERY_RANGE", source)
        self.assertNotIn("subprocess.Popen", source)
        self.assertIn("ClearEntireCostmap", source)


if __name__ == "__main__":
    unittest.main()
