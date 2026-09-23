from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "hooks" / "user_input_guard.py"
spec = importlib.util.spec_from_file_location("user_input_guard", MODULE_PATH)
assert spec and spec.loader
user_input_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(user_input_guard)


class UserInputGuardTests(unittest.TestCase):
    def test_root_sync_user_input_is_allowed(self) -> None:
        self.assertIsNone(
            user_input_guard.block_reason({
                "tool_name": "request_user_input",
                "agent_id": None,
                "agent_type": None,
            })
        )

    def test_subagent_sync_user_input_is_blocked(self) -> None:
        reason = user_input_guard.block_reason({
            "tool_name": "request_user_input",
            "agent_id": "agent-123",
            "agent_type": "worker",
        })
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("root session", reason.lower())
        self.assertIn("CONDUCTOR_USER_QUESTION", reason)

    def test_subagent_async_user_input_is_blocked(self) -> None:
        reason = user_input_guard.block_reason({
            "tool_name": "request_user_input_async",
            "agent_id": "agent-123",
        })
        self.assertIsNotNone(reason)

    def test_unrelated_tool_is_ignored(self) -> None:
        self.assertIsNone(
            user_input_guard.block_reason({
                "tool_name": "shell",
                "agent_id": "agent-123",
            })
        )


if __name__ == "__main__":
    unittest.main()
