# Codex Conductor

Codex Conductor is a lightweight, persistent task-orchestration plugin for Codex projects.

It is designed for a workflow where the **root Codex session remains the only conversation the user needs to follow**, while Conductor quietly maintains project context and may use **at most one focused worker subagent at a time** when a task benefits from stronger reasoning or isolated focus.

## Goals

- Keep long-lived project state outside chat history.
- Turn meaningful work into a small dependency-aware task graph.
- Resume cleanly after days or weeks away from a project.
- Keep trivial work trivial instead of turning every edit into project-management overhead.
- Keep the root session lightweight and cost-efficient.
- Allow one worker at a time for harder bounded work.
- Route worker questions back to the root session instead of requiring the user to switch conversations.
- Provide a stable state contract that reusable project skills can share.

## Runtime model

Conductor's default policy is:

- **Root session:** `gpt-5.6-luna` is the preferred cost-efficient baseline.
- **Medium worker task:** prefer `gpt-5.6-terra` when a worker is justified.
- **Complex/high-risk worker task:** prefer `gpt-5.6-sol`.
- **Maximum active workers:** `1`.

The plugin injects this routing policy as context. It does **not** claim to override a host that does not expose per-worker model selection.

## Current plugin structure

```text
codex-conductor/
├── plugin.json
├── hooks/
│   ├── hooks.json
│   └── conductor.py
├── scripts/
│   └── bootstrap.py
├── docs/
│   └── state-schema.md
├── tests/
│   └── test_conductor.py
└── .agents/plugins/
    └── marketplace.json
```

## Lifecycle hooks

Conductor currently uses:

- `SessionStart` — inject a compact persistent project snapshot.
- `UserPromptSubmit` — remind the root session to classify and synchronize meaningful project work.
- `PreToolUse` for agent tools — reserve the single worker slot and reject a second simultaneous worker.
- `SubagentStart` — inject the worker contract and prohibit nested agents/project-state edits.
- `SubagentStop` — route worker results or user questions back into the root flow.
- `Stop` — currently non-blocking; reserved for later consistency checks.

## Project state

Projects use a `.conductor/` directory:

```text
.conductor/
├── project.json
├── state.json
├── tasks.json
├── decisions.json
└── config.json
```

See [`docs/state-schema.md`](docs/state-schema.md) for the v1 contract.

The root session owns these files. Workers are instructed not to edit them.

## Bootstrap a project manually

Until the planned `project-setup` skill exists, a state directory can be created manually:

```bash
python3 scripts/bootstrap.py --name GearMastery --kind minecraft-plugin
```

The future setup skill will own richer technology/framework discovery and update these files instead of relying on this minimal bootstrap command.

## Local development / installation

The repository includes a repo marketplace definition under `.agents/plugins/marketplace.json`.

Add the marketplace:

```bash
codex plugin marketplace add s3tupw1zard/codex-conductor
```

Then install/enable **Codex Conductor** from the Plugins Directory in a supported local ChatGPT/Codex client and review/trust its hooks.

Plugin hooks are not trusted automatically. Review `hooks/hooks.json` and `hooks/conductor.py` before approving them.

## Tests

No third-party Python packages are required.

```bash
python3 -m unittest discover -s tests -v
```

## Planned companion skills

The plugin intentionally does not encode the whole development methodology. Separate reusable skills will share the Conductor state contract, including:

- project setup / project context update
- project status
- discovery
- GitHub Selection Gate
- product specification
- technical design / developer contracts
- implementation
- controlled change
- debugging
- verification

This separation keeps Conductor passive: normal prompts and explicit skill commands remain the user's primary interaction model.

## Development status

`0.1.0` is the initial runtime scaffold. Before treating it as stable, it still needs live Codex testing for:

- exact agent-tool matcher behavior across current Codex builds,
- explicit per-worker model selection,
- worker resume via `followup_task`,
- question handoff behavior,
- stale worker-lock recovery,
- and ChatGPT Work/local-runtime differences for command hooks.
