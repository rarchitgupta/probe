from __future__ import annotations

import unittest

from qa_agent.policy import ExecutionGuard, ExecutionPolicy, PolicyViolation, origin


class ExecutionPolicyTest(unittest.TestCase):
    def test_defaults_to_starting_origin(self) -> None:
        policy = ExecutionPolicy().for_start_url("https://example.com/login")
        guard = ExecutionGuard(policy)

        guard.check_url("https://example.com/account")
        with self.assertRaises(PolicyViolation):
            guard.check_url("https://other.example/account")

    def test_enforces_action_limit(self) -> None:
        guard = ExecutionGuard(
            ExecutionPolicy(max_actions=1).for_start_url("data:text/html,hello")
        )

        guard.record_action()
        with self.assertRaises(PolicyViolation):
            guard.record_action()

    def test_normalizes_origins(self) -> None:
        self.assertEqual(origin("https://example.com/path"), "https://example.com")
        self.assertEqual(origin("data:text/html,hello"), "data:")


if __name__ == "__main__":
    unittest.main()
