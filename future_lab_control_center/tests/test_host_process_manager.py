import importlib.util
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


AGENT_PATH = Path(__file__).resolve().parents[1] / "host_agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location("future_lab_host_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


class ProcessManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.marker = f"future-lab-process-test-{uuid.uuid4()}"
        self.command = [
            "/usr/bin/python3",
            "-c",
            "import time; time.sleep(30)",
            self.marker,
        ]
        spec = agent.LaunchSpec(
            command=(
                "exec /usr/bin/python3 -c 'import time; time.sleep(30)' "
                f"{self.marker}"
            ),
            log_path=Path(self.tmp.name) / "process.log",
            markers=(self.marker,),
        )
        self.manager = agent.ProcessManager({"test": spec})

    def tearDown(self):
        try:
            self.manager.stop("test")
        finally:
            self.tmp.cleanup()

    def test_start_is_idempotent_and_stop_is_confirmed(self):
        started = self.manager.start("test")
        self.assertEqual("process_started", started["status"])
        self.assertTrue(started["process"]["running"])
        self.assertEqual(1, started["process"]["instances"])
        self.assertTrue(started["process"]["owned"])

        with self.assertRaises(agent.ProcessConflict):
            self.manager.start("test")

        stopped = self.manager.stop("test")
        self.assertEqual("stopped", stopped["status"])
        self.assertEqual([], stopped["survivors"])
        self.assertFalse(self.manager.status("test")["running"])

    def test_stop_is_safe_when_already_stopped(self):
        result = self.manager.stop("test")
        self.assertEqual("already_stopped", result["status"])
        self.assertEqual([], result["survivors"])

    def test_custom_nav2_launch_is_recognized(self):
        argv = [
            "/usr/bin/python3",
            "/opt/ros/jazzy/bin/ros2",
            "launch",
            "/workspace/turtlebot4_jazzy/launch/nav2_lifecycle_timeout.launch.py",
        ]
        self.assertTrue(
            agent._matches(
                "nav2",
                agent.LAUNCH_SPECS["nav2"],
                argv,
                "/usr/bin/python3.12",
                " ".join(argv),
            )
        )

    def test_custom_localization_launch_is_recognized(self):
        argv = [
            "/usr/bin/python3",
            "/opt/ros/jazzy/bin/ros2",
            "launch",
            "/workspace/turtlebot4_jazzy/launch/localization_lifecycle_timeout.launch.py",
        ]
        self.assertTrue(
            agent._matches(
                "localization",
                agent.LAUNCH_SPECS["localization"],
                argv,
                "/usr/bin/python3.12",
                " ".join(argv),
            )
        )

    def test_stop_cleans_multiple_unmanaged_generations(self):
        processes = [
            subprocess.Popen(
                self.command,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ),
            subprocess.Popen(
                self.command,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ),
        ]
        try:
            time.sleep(0.1)
            status = self.manager.status("test")
            self.assertEqual(2, status["instances"])
            self.assertFalse(status["owned"])
            self.assertIsNotNone(status["error"])

            result = self.manager.stop("test")
            self.assertEqual("stopped", result["status"])
            self.assertEqual(2, len(result["stopped_groups"]))
            self.assertFalse(self.manager.status("test")["running"])
        finally:
            for proc in processes:
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()


class InitialPoseHostRunnerTest(unittest.TestCase):
    def test_success_requires_helper_json_ok(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"ok": true, "pose": {"x": 1.0}, "confirmation_source": "amcl_log_setting_pose"}\n',
            stderr="",
        )
        with patch.object(agent.subprocess, "run", return_value=completed):
            result, code = agent.run_initial_pose(1.0, 2.0, 0.5)
        self.assertEqual(200, code)
        self.assertTrue(result["ok"])

    def test_nonzero_helper_is_not_success(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=1,
            stdout='{"ok": false, "error": "AMCL sem confirmacao"}\n',
            stderr="",
        )
        with patch.object(agent.subprocess, "run", return_value=completed):
            result, code = agent.run_initial_pose(1.0, 2.0, 0.5)
        self.assertEqual(503, code)
        self.assertIn("AMCL sem confirmacao", result["detail"])

    def test_rejects_nonfinite_coordinates_without_subprocess(self):
        with patch.object(agent.subprocess, "run") as run:
            _result, code = agent.run_initial_pose(float("nan"), 2.0, 0.5)
        self.assertEqual(422, code)
        run.assert_not_called()


class TriggerServiceHostRunnerTest(unittest.TestCase):
    def test_success_requires_measured_server_response(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"responded": true, "success": true, "message": "aceita"}\n',
            stderr="",
        )
        with patch.object(agent.subprocess, "run", return_value=completed):
            result, code = agent.run_trigger_service("start_delivery")
        self.assertEqual(200, code)
        self.assertTrue(result["responded"])
        self.assertTrue(result["success"])

    def test_response_timeout_is_ambiguous_and_not_success(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=4,
            stdout=(
                '{"responded": false, "request_sent": true, '
                '"error": "sem resposta"}\n'
            ),
            stderr="",
        )
        with patch.object(agent.subprocess, "run", return_value=completed):
            result, code = agent.run_trigger_service("start_delivery")
        self.assertEqual(504, code)
        self.assertFalse(result["responded"])

    def test_rejects_service_outside_allowlist(self):
        with patch.object(agent.subprocess, "run") as run:
            result, code = agent.run_trigger_service("robot_power")
        self.assertEqual(422, code)
        self.assertIn("não permitido", result["detail"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
