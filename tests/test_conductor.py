from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "hooks" / "conductor.py"
HOOKS_PATH = Path(__file__).resolve().parents[1] / "hooks" / "hooks.json"
spec = importlib.util.spec_from_file_location("conductor", MODULE_PATH)
assert spec and spec.loader
conductor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conductor)


class ConductorTests(unittest.TestCase):
    def test_project_snapshot_without_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = conductor.project_snapshot(Path(tmp))
            self.assertIn("not initialized", snapshot)

    def test_minimal_state_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = conductor.ensure_minimal_state(root)
            self.assertTrue(created)
            self.assertTrue((root / ".conductor" / "project.json").is_file())
            project = json.loads((root / ".conductor" / "project.json").read_text(encoding="utf-8"))
            config = json.loads((root / ".conductor" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(project["profile_state"], "incomplete")
            self.assertEqual(config["routing"]["root_model_hint"], "gpt-6-luna")

    def test_trivial_prompts_do_not_auto_initialize(self) -> None:
        self.assertTrue(conductor.is_trivial_prompt("Danke"))
        self.assertFalse(conductor.is_trivial_prompt("Implementiere eine kleine CLI"))

    def test_prompt_submit_auto_initializes_meaningful_git_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = io.StringIO()
            with (
                mock.patch.object(conductor, "project_root", return_value=root),
                mock.patch.object(conductor, "git_root", return_value=root),
                redirect_stdout(out),
            ):
                conductor.handle_prompt_submit({"cwd": str(root), "prompt": "Implementiere eine kleine CLI"})
            self.assertTrue((root / ".conductor" / "project.json").is_file())
            payload = json.loads(out.getvalue())
            self.assertIn("Initialized minimal .conductor project state automatically.", payload.get("systemMessage", ""))

    def test_project_snapshot_summarizes_tasks_and_blocking_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conductor.ensure_minimal_state(root)
            state = root / ".conductor"
            (state / "project.json").write_text(json.dumps({"name": "GearMastery", "kind": "minecraft-plugin"}), encoding="utf-8")
            (state / "state.json").write_text(json.dumps({"phase": "specification", "current_task_id": "SPEC-2"}), encoding="utf-8")
            (state / "tasks.json").write_text(json.dumps({"tasks": [
                {"id": "SPEC-2", "title": "Define leveling", "status": "waiting_for_user"},
                {"id": "DESIGN-1", "title": "Design persistence", "status": "blocked"}
            ]}), encoding="utf-8")
            (state / "decisions.json").write_text(json.dumps({"decisions": [
                {"id": "DEC-1", "question": "Keep XP on rename?", "status": "open", "blocking": True}
            ]}), encoding="utf-8")
            snapshot = conductor.project_snapshot(root)
            self.assertIn("GearMastery", snapshot)
            self.assertIn("SPEC-2", snapshot)
            self.assertIn("DESIGN-1", snapshot)
            self.assertIn("BLOCKING user decisions", snapshot)
            self.assertIn("DEC-1", snapshot)

    def test_async_question_is_denied_in_tracked_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conductor.ensure_minimal_state(root)
            out = io.StringIO()
            with mock.patch.object(conductor, "project_root", return_value=root), redirect_stdout(out):
                conductor.reserve_or_guard_tool({"cwd": str(root), "tool_name": "request_user_input_async"})
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn("synchronous request_user_input", payload["hookSpecificOutput"]["permissionDecisionReason"])

    def test_stop_blocks_unresolved_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conductor.ensure_minimal_state(root)
            decisions = root / ".conductor" / "decisions.json"
            decisions.write_text(json.dumps({"decisions": [
                {"id": "DEC-7", "question": "Which behavior?", "status": "open", "blocking": True}
            ]}), encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(conductor, "project_root", return_value=root), redirect_stdout(out):
                conductor.handle_stop({"cwd": str(root)})
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["decision"], "block")
            self.assertIn("DEC-7", payload["reason"])

    def test_external_wait_allows_turn_to_end_but_still_blocks_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conductor.ensure_minimal_state(root)
            decisions = root / ".conductor" / "decisions.json"
            decisions.write_text(json.dumps({"decisions": [
                {"id": "DEC-8", "question": "Need user", "status": "waiting_for_user_external", "blocking": True}
            ]}), encoding="utf-8")
            self.assertEqual(conductor.stop_blocking_decisions(root), [])
            self.assertEqual(len(conductor.blocking_decisions(root)), 1)

    def test_runtime_lock_blocks_second_worker_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"PLUGIN_DATA": tmp}):
                conductor.write_runtime("session", {"state": "active", "agent_id": "agent-1"})
                current = conductor.read_runtime("session")
                self.assertEqual(current["state"], "active")
                self.assertEqual(current["agent_id"], "agent-1")

    def test_every_command_hook_has_windows_override(self) -> None:
        hooks = json.loads(HOOKS_PATH.read_text(encoding="utf-8"))["hooks"]
        commands = [
            handler
            for groups in hooks.values()
            for group in groups
            for handler in group.get("hooks", [])
            if handler.get("type") == "command"
        ]
        self.assertGreater(len(commands), 0)
        for handler in commands:
            self.assertIn("commandWindows", handler)
            self.assertIn("python", handler["commandWindows"].lower())
            self.assertIn("%PLUGIN_ROOT%", handler["commandWindows"])


if __name__ == "__main__":
    unittest.main()
