import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


AGENT_DIR = Path(__file__).resolve().parents[1] / "host_agent"
sys.path.insert(0, str(AGENT_DIR))
MODULE_PATH = AGENT_DIR / "mission_signal_agent.py"
SPEC = importlib.util.spec_from_file_location("future_lab_mission_signal_agent", MODULE_PATH)
signal_agent = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(signal_agent)


class MissionSignalAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "mission.log"
        self.log_path.write_text("linha antiga\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def completed(self):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                '{"published": true, "topic": "/product_class", '
                '"value": "tin_valid_red", "subscriber_count": 1, '
                '"published_count": 10}\n'
            ),
            stderr="",
        )

    def test_success_requires_new_delivery_log_line(self):
        marker = "Tópico /product_class recebido no TurtleBot 4: 'tin_valid_red'"

        def publish(*_args, **_kwargs):
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(f"[INFO] [123.4] [delivery_routine]: {marker}\n")
            return self.completed()

        with (
            patch.object(signal_agent, "MISSION_LOG", self.log_path),
            patch.object(signal_agent.subprocess, "run", side_effect=publish),
        ):
            result, code = signal_agent.publish_and_confirm(
                "product_class", "tin_valid_red"
            )
        self.assertEqual(200, code)
        self.assertTrue(result["received_by_mission"])
        self.assertEqual(123.4, result["received_log_timestamp"])

    def test_invalid_value_does_not_start_publisher(self):
        with patch.object(signal_agent.subprocess, "run") as run:
            result, code = signal_agent.publish_and_confirm("product_class", "green")
        self.assertEqual(422, code)
        self.assertIn("não permitido", result["detail"])
        run.assert_not_called()

    def test_delivery_requires_new_trigger_and_exact_target_evidence(self):
        process = MagicMock()
        process.poll.return_value = None
        process.communicate.return_value = ("", "")
        timestamps = iter((10.0, 20.0, 30.0, 11.0, 21.0, 31.0))
        with (
            patch.object(
                signal_agent,
                "_latest_marker_timestamp",
                side_effect=lambda _marker: next(timestamps),
            ),
            patch.object(signal_agent.subprocess, "Popen", return_value=process),
        ):
            result, code = signal_agent.start_delivery_and_confirm(
                "tin_valid_blue"
            )

        self.assertEqual(200, code)
        self.assertTrue(result["started"])
        self.assertEqual("delivery_blue", result["target"])
        process.terminate.assert_called_once()

    def test_delivery_rejects_unknown_class_without_starting_helper(self):
        with patch.object(signal_agent.subprocess, "Popen") as popen:
            result, code = signal_agent.start_delivery_and_confirm(
                "tin_valid_green"
            )

        self.assertEqual(422, code)
        self.assertIn("não permitida", result["detail"])
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
