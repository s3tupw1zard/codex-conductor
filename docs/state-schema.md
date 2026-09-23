# Project state contract (v1)

Codex Conductor stores durable, project-owned state in `.conductor/`.
Runtime-only worker locks live in the plugin data directory and are not committed to the project.

A minimal state is created automatically on the first meaningful prompt inside a Git repository. The later project-setup skill enriches that state with language, framework, build-system, and compatibility details.

## `.conductor/project.json`

Describes stable project context.

```json
{
  "schema_version": 1,
  "name": "GearMastery",
  "kind": "minecraft-plugin",
  "profile_state": "complete",
  "technologies": ["java"],
  "frameworks": ["paper"],
  "constraints": [],
  "initialized_by": "project-setup",
  "created_at": "2026-09-23T12:00:00Z",
  "updated_at": "2026-09-23T12:00:00Z"
}
```

Auto-initialized projects start with `kind: "generic"` and `profile_state: "incomplete"`.

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
      "status": "waiting_for_user",
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

Stores product/user decisions that must not be guessed by Codex or a worker.

```json
{
  "schema_version": 1,
  "decisions": [
    {
      "id": "DEC-001",
      "source_task": "SPEC-004",
      "question": "Should item XP survive an anvil rename?",
      "blocking": true,
      "status": "open",
      "options": [
        {
          "label": "Preserve level and XP (Recommended)",
          "description": "The item keeps all progression when renamed."
        },
        {
          "label": "Reset progression",
          "description": "Renaming removes the stored progression."
        }
      ],
      "recommended_option": "Preserve level and XP",
      "answer": null,
      "additional_context": null,
      "asked_via": "request_user_input",
      "created_at": "2026-09-23T12:00:00Z",
      "resolved_at": null
    }
  ]
}
```

Recommended decision statuses:

- `open` — decision exists but has not been resolved
- `pending` — equivalent unresolved state used during preparation
- `waiting_for_user` — a synchronous decision flow is active
- `waiting_for_user_external` — synchronous UI was unavailable and the root asked in normal chat; the turn may end while waiting
- `resolved`
- `superseded`

Blocking decisions prevent dependent worker execution. A Stop hook also prevents Codex from finishing while ordinary unresolved blocking decisions remain. `waiting_for_user_external` is the fallback exception so the root can end the turn and wait for a normal user reply.

### Interactive question batches

For blocking decisions, Conductor instructs the root to use synchronous `request_user_input` rather than `request_user_input_async`.

- Ask at most two substantive blocking questions per batch.
- Each substantive question should have 2-3 mutually exclusive options.
- Put the recommended option first and suffix its label with `(Recommended)`.
- Do not create an `Other` option; Codex adds free-form `Other` automatically.
- When there is room, use the third tab for `additional_context`, allowing the user to add anything else that should influence the decision.
- Persist the selected/free-form answer and any extra context before unblocking dependent tasks.

## `.conductor/config.json`

Project-level routing and interaction hints. These are policy hints, not guarantees that the host can force a model switch.

```json
{
  "schema_version": 1,
  "routing": {
    "root_model_hint": "gpt-6-luna",
    "worker_medium_model": "gpt-5.6-terra",
    "worker_complex_model": "gpt-5.6-sol",
    "max_active_workers": 1
  },
  "decisions": {
    "blocking_input_mode": "sync",
    "max_substantive_questions_per_batch": 2,
    "include_additional_context_tab": true
  }
}
```

## Ownership rules

- The root Codex session owns `.conductor/` updates.
- Worker subagents must not modify `.conductor/`.
- User/product questions become blocking decisions and are surfaced in the root session.
- Workers stop at a safe boundary instead of guessing when user input is required.
- The task graph should be the minimum useful graph, not a decomposition of every tiny edit.
- Selection Gate state references GitHub issues; the issue remains the authoritative human selection surface while it is active.
