import threading
import time
import unittest
from unittest.mock import patch

from backend.ros2_nodes import turtlebot_node as module


class TurtleBotSingletonTest(unittest.TestCase):
    def setUp(self):
        self.previous_node = module._tb_node
        module._tb_node = None

    def tearDown(self):
        module._tb_node = self.previous_node

    def test_concurrent_requests_construct_exactly_one_node(self):
        workers = 12
        start = threading.Barrier(workers)
        constructed = 0
        constructed_lock = threading.Lock()

        class FakeTurtleBotNode:
            def __init__(self):
                nonlocal constructed
                with constructed_lock:
                    constructed += 1
                # Amplia deterministicamente a janela da antiga corrida.
                time.sleep(0.02)

        instances = []

        def get_node():
            start.wait()
            instances.append(module.get_turtlebot_node())

        with patch.object(module, "TurtleBotNode", FakeTurtleBotNode):
            threads = [threading.Thread(target=get_node) for _ in range(workers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=1.0)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(1, constructed)
        self.assertEqual(1, len({id(instance) for instance in instances}))


if __name__ == "__main__":
    unittest.main()
