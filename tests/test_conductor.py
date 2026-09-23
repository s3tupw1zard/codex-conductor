from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "hooks" / "conductor.py"
spec = importlib.util.spec_from_file_location("conductor", MODULE_PATH)
assert spec and spec.loader
conductor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conductor)


class ConductorTests(unittest.TestCase):
    def test_project_snapshot_without_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = conductor.project_snapshot(Path(tmp))
            self.assertIn("not initialized", snapshot)

    def test_project_snapshot_summarizes_tasks_and_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".conductor"
            state.mkdir()
            (state / "project.json").write_text(json.dumps({"name": "GearMastery", "kind": "minecraft-plugin"}))
            (state / "state.json").write_text(json.dumps({"phase": "specification", "current_task_id": "SPEC-2"}))
            (state / "tasks.json").write_text(
                json.dumps(
                    {
                        "tasks": [
                            {"id": "SPEC-2", "title": "Define leveling", "status": "in_progress"},
                            {"id": "DESIGN-1", "title": "Design persistence", "status": "blocked"}
                        ]
                    }
                )
            )
            (state / "decisions.json").write_text(
                json.dumps({"decisions": [{"id": "DEC-1", "question": "Keep XP on rename?", "status": "open"}]})
            )
            snapshot = conductor.project_snapshot(root)
            self.assertIn("GearMastery", snapshot)
            self.assertIn("SPEC-2", snapshot)
            self.assertIn("DESIGN-1", snapshot)
            self.assertIn("DEC-1", snapshot)

    def test_runtime_lock_blocks_second_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"PLUGIN_DATA": tmp}):
                conductor.write_runtime("session", {"state": "active", "agent_id": "agent-1"})
                current = conductor.read_runtime("session")
                self.assertEqual(current["state"], "active")
                self.assertEqual(current["agent_id"], "agent-1")


if __name__ == "__main__":
    unittest.main()
