# Codex Conductor

Codex Conductor is a lightweight, persistent task-orchestration plugin for Codex projects.

The **root Codex session remains the user's only conversational interface**. Conductor maintains durable project state, may use at most one focused worker subagent at a time, and routes every user-facing decision back through the root session.

## Runtime model

- **Root session:** prefer `gpt-6-luna`.
- **Medium worker task:** prefer `gpt-5.6-terra` when justified.
- **Complex/high-risk worker task:** prefer `gpt-5.6-sol`.
- **Maximum active workers:** `1`.

These are routing hints; the plugin does not claim to override a host that does not expose per-worker model selection.

## Required Codex feature for interactive decisions

Conductor uses Codex's synchronous `request_user_input` tool for native interactive blocking-decision menus.

In normal **Default** collaboration mode, current Codex builds require:

```toml
[features]
plugins = true
default_mode_request_user_input = true
```

Restart Codex after changing `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`). Verify with:

```bash
python scripts/doctor.py
```

See [`docs/interactive-input.md`](docs/interactive-input.md).

## Current plugin structure

```text
codex-conductor/
├── plugin.json
├── hooks/
│   ├── hooks.json
│   ├── conductor.py
│   ├── decision_ui_policy.py
│   └── user_input_guard.py
├── scripts/
│   ├── bootstrap.py
│   └── doctor.py
├── docs/
│   ├── interactive-input.md
│   ├── live-test.md
│   └── state-schema.md
└── tests/
```

The plugin is published through the separate [`s3tupw1zard/codex-plugins`](https://github.com/s3tupw1zard/codex-plugins) marketplace rather than carrying its own marketplace definition.

## Lifecycle behavior

- `SessionStart` injects a compact persistent project snapshot.
- `UserPromptSubmit` automatically initializes minimal state on the first meaningful prompt in a Git repository and injects the decision UI policy.
- `PreToolUse` enforces the worker slot, denies asynchronous project questions, and prevents workers from calling either user-input tool.
- `SubagentStart` applies the worker contract.
- `SubagentStop` routes worker results or `CONDUCTOR_USER_QUESTION` handoffs back into the root flow.
- `Stop` prevents dependent work from silently completing around unresolved blocking decisions.

## Automatic project initialization

The first meaningful project prompt creates:

```text
.conductor/
├── project.json
├── state.json
├── tasks.json
├── decisions.json
└── config.json
```

The initial profile is deliberately generic and can later be enriched by a project-setup skill.

## Blocking decisions

A missing product decision, preference, approval, requirement, or scope choice that changes the result is blocking.

```text
work reaches unresolved choice
        ↓
record decision + block dependent task
        ↓
ROOT request_user_input
        ↓
user answers
        ↓
persist answer
        ↓
unblock satisfied work
```

For native questions, Conductor aims for at most two substantive questions plus a third `Zusatz` question for extra context. Each substantive question should provide 2-3 mutually exclusive options; the native client supplies the free-form `Other` path.

## Worker question handoff

Workers never own user interaction.

If a worker needs user input, it must return a structured handoff containing `CONDUCTOR_USER_QUESTION`. Conductor has a dedicated `PreToolUse` guard for `request_user_input` and `request_user_input_async`: Codex supplies `agent_id` / `agent_type` for subagent tool calls, and those calls are denied before the worker can open its own question surface.

The root session then:

1. persists the blocking decision,
2. opens the native interactive menu,
3. stores the answer,
4. resumes the same worker with `followup_task` when useful.

The user should not need to reveal or switch into a worker thread to answer a question.

## Installation

Codex Conductor is distributed through the **`s3tupw1zard`** marketplace.

Add the marketplace once:

```bash
codex plugin marketplace add s3tupw1zard/codex-plugins
```

Then install Conductor:

```bash
codex plugin add codex-conductor@s3tupw1zard
```

After marketplace/plugin updates:

```bash
codex plugin marketplace upgrade s3tupw1zard
codex plugin add codex-conductor@s3tupw1zard
```

Restart Codex after refreshing the plugin.

During the initial live-test phase, the marketplace entry points at this repository's `feat/initial-conductor-runtime` branch. It will move to `main` after the initial runtime PR is merged.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Coverage includes state creation, task/decision snapshots, blocking decisions, async-question denial, Stop gating, worker locking, Windows hook overrides, and root-only user-input enforcement.

## Planned companion skills

The plugin intentionally stays separate from the full development methodology. Planned skills include project setup/context, project status, discovery, GitHub Selection Gate, product specification, technical design/contracts, implementation, controlled change, debugging, and verification.

## Development status

`0.1.3` is a live-test build. Important remaining live checks include native root-session question placement, same-worker resume after user input, explicit worker model routing, stale lock recovery, and ChatGPT Work/runtime differences.
