#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize Codex Conductor state for a project.")
    parser.add_argument("--root", default=".", help="Project root. Defaults to the current directory.")
    parser.add_argument("--name", required=True, help="Human-readable project name.")
    parser.add_argument("--kind", default="generic", help="Project kind, e.g. minecraft-plugin, web-app, cli.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing .conductor directory.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    state_dir = root / ".conductor"
    if state_dir.exists() and not args.force:
        raise SystemExit(f"{state_dir} already exists; pass --force to replace its files")

    state_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now_iso()

    write_json(
        state_dir / "project.json",
        {
            "schema_version": 1,
            "name": args.name,
            "kind": args.kind,
            "profile_state": "incomplete",
            "technologies": [],
            "frameworks": [],
            "constraints": [],
            "initialized_by": "manual-bootstrap",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )
    write_json(
        state_dir / "state.json",
        {
            "schema_version": 1,
            "phase": "discovery",
            "current_task_id": None,
            "last_completed_task_id": None,
            "selection_gate": None,
            "updated_at": timestamp,
        },
    )
    write_json(state_dir / "tasks.json", {"schema_version": 1, "tasks": []})
    write_json(state_dir / "decisions.json", {"schema_version": 1, "decisions": []})
    write_json(
        state_dir / "config.json",
        {
            "schema_version": 1,
            "routing": {
                "root_model_hint": "gpt-6-luna",
                "worker_medium_model": "gpt-5.6-terra",
                "worker_complex_model": "gpt-5.6-sol",
                "max_active_workers": 1,
            },
            "decisions": {
                "blocking_input_mode": "sync",
                "max_substantive_questions_per_batch": 2,
                "include_additional_context_tab": True,
            },
        },
    )
    print(f"Initialized Codex Conductor state in {state_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
