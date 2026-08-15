import threading
import time
import types
import unittest

from action_msgs.msg import GoalInfo, GoalStatus
from action_msgs.srv import CancelGoal

from backend.ros2_nodes import turtlebot_node as module


class FakeFuture:
    def __init__(self, result):
        self._result = result

    def done(self):
        return True

    def result(self):
        return self._result


class FakeClient:
    def __init__(self, response, available=True):
        self.response = response
        self.available = available

    def wait_for_service(self, timeout_sec):
        return self.available

    def call_async(self, request):
        return FakeFuture(self.response)


def response(code, goal_ids=()):
    msg = CancelGoal.Response()
    msg.return_code = code
    for raw_id in goal_ids:
        info = GoalInfo()
        info.goal_id.uuid = list(raw_id)
        msg.goals_canceling.append(info)
    return msg


def fake_node(cancel_response, statuses=None):
    node = types.SimpleNamespace()
    node.cancel_nav_client = FakeClient(cancel_response)
    node._nav_status_lock = threading.Lock()
    node._nav_goal_statuses = dict(statuses or {})
    node.last_nav_status_time = time.time() + 60.0
    node._nav_goals_still_active = types.MethodType(
        module.TurtleBotNode._nav_goals_still_active, node
    )
    return node


class CancelAllNavGoalsTest(unittest.TestCase):
    def call(self, node, confirm_sec=0.1):
        return module.TurtleBotNode.cancel_all_nav_goals(
            node, timeout_sec=0.1, confirm_sec=confirm_sec
        )

    def test_rejected_is_not_success(self):
        node = fake_node(response(CancelGoal.Response.ERROR_REJECTED))
        ok, count, message = self.call(node)
        self.assertFalse(ok)
        self.assertEqual(0, count)
        self.assertIn("rejeitou", message)

    def test_no_active_goal_is_confirmed(self):
        node = fake_node(response(CancelGoal.Response.ERROR_NONE))
        ok, count, _ = self.call(node)
        self.assertTrue(ok)
        self.assertEqual(0, count)

    def test_goal_must_leave_active_states(self):
        goal_id = bytes(range(16))
        node = fake_node(
            response(CancelGoal.Response.ERROR_NONE, [goal_id]),
            {goal_id: GoalStatus.STATUS_EXECUTING},
        )

        def finish_cancel():
            time.sleep(0.03)
            with node._nav_status_lock:
                node._nav_goal_statuses[goal_id] = GoalStatus.STATUS_CANCELED
                node.last_nav_status_time = time.time()

        threading.Thread(target=finish_cancel, daemon=True).start()
        ok, count, message = self.call(node, confirm_sec=0.3)
        self.assertTrue(ok, message)
        self.assertEqual(1, count)

    def test_still_executing_is_not_success(self):
        goal_id = bytes(range(16))
        node = fake_node(
            response(CancelGoal.Response.ERROR_NONE, [goal_id]),
            {goal_id: GoalStatus.STATUS_EXECUTING},
        )
        ok, count, message = self.call(node, confirm_sec=0.05)
        self.assertFalse(ok)
        self.assertEqual(1, count)
        self.assertIn("continuaram ativas", message)

    def test_missing_status_transition_is_not_success(self):
        goal_id = bytes(range(16))
        node = fake_node(response(CancelGoal.Response.ERROR_NONE, [goal_id]))
        node.last_nav_status_time = 0.0
        ok, count, message = self.call(node, confirm_sec=0.05)
        self.assertFalse(ok)
        self.assertEqual(1, count)
        self.assertIn("nao confirmou", message)


if __name__ == "__main__":
    unittest.main()
