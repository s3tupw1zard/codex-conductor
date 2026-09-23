# Project state contract (v1)

Codex Conductor stores durable, project-owned state in `.conductor/`.
Runtime-only worker locks live in the plugin data directory and are not committed to the project.

## `.conductor/project.json`

Describes stable project context. The later `project-setup` and project-context skills are expected to maintain this file.

```json
{
  "schema_version": 1,
  "name": "GearMastery",
  "kind": "minecraft-plugin",
  "technologies": ["java"],
  "frameworks": ["paper"],
  "constraints": [],
  "created_at": "2026-09-23T12:00:00Z",
  "updated_at": "2026-09-23T12:00:00Z"
}
```

## `.conductor/state.json`

Stores the current workflow phase and the task/selection pointers required to resume work later.

```json
{
  "schema_version": 1,
  "phase": "specification",
  "current_task_id": "SPEC-004",
  "last_completed_task_id": "SPEC-003",
  "selection_gate": {
    "provider": "github",
    "issue": 12,
    "state": "selecting"
  },
  "updated_at": "2026-09-23T12:00:00Z"
}
```

## `.conductor/tasks.json`

The task graph. Dependencies are directional: `depends_on` names prerequisites for the task.

Recommended statuses:

- `proposed`
- `ready`
- `in_progress`
- `waiting_for_user`
- `blocked`
- `done`
- `skipped`

Recommended task types:

- `discovery`
- `specification`
- `design`
- `contract`
- `implementation`
- `verification`
- `debug`
- `documentation`
- `maintenance`

```json
{
  "schema_version": 1,
  "tasks": [
    {
      "id": "SPEC-004",
      "title": "Define item XP overflow behavior",
      "type": "specification",
      "status": "in_progress",
      "priority": "normal",
      "depends_on": ["SPEC-003"],
      "blocks": ["DESIGN-002"],
      "artifacts": ["docs/user/leveling.md"],
      "notes": []
    }
  ]
}
```

## `.conductor/decisions.json`

Stores questions that require a user/product decision instead of a technical assumption.

```json
{
  "schema_version": 1,
  "decisions": [
    {
      "id": "DEC-001",
      "source_task": "SPEC-004",
      "question": "Should item XP survive an anvil rename?",
      "status": "open",
      "answer": null
    }
  ]
}
```

Recommended decision statuses:

- `open`
- `resolved`
- `superseded`

## `.conductor/config.json`

Project-level routing hints. These are policy hints, not guarantees that the host can force a model switch.

```json
{
  "schema_version": 1,
  "routing": {
    "root_model_hint": "gpt-5.6-luna",
    "worker_medium_model": "gpt-5.6-terra",
    "worker_complex_model": "gpt-5.6-sol",
    "max_active_workers": 1
  }
}
```

## Ownership rules

- The root Codex session owns `.conductor/` updates.
- Worker subagents must not modify `.conductor/`.
- User/product questions become decisions and are surfaced in the root session.
- The task graph should be the minimum useful graph, not a decomposition of every tiny edit.
- Selection Gate state references GitHub issues; the issue remains the authoritative human selection surface while it is active.
