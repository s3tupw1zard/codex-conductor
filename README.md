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
- Block dependent work when a product/user decision is unresolved.
- Provide a stable state contract that reusable project skills can share.

## Runtime model

Conductor's default policy is:

- **Root session:** `gpt-6-luna` is the preferred lightweight baseline.
- **Medium worker task:** prefer `gpt-5.6-terra` when a worker is justified.
- **Complex/high-risk worker task:** prefer `gpt-5.6-sol`.
- **Maximum active workers:** `1`.

The plugin injects this routing policy as context. It does **not** claim to override a host that does not expose per-worker model selection.

## Required Codex feature for interactive decisions

Conductor's blocking decision flow uses Codex's synchronous `request_user_input` tool to render an interactive selection UI and wait for the answer.

In the normal **Default** Codex collaboration mode, current Codex builds require the following feature flag:

```toml
[features]
plugins = true
default_mode_request_user_input = true
```

Restart Codex after changing `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`). Without this host feature, Conductor can still stop and wait, but Codex can only fall back to a plain-text question instead of the native interactive menu.

You can verify the prerequisite with:

```bash
python scripts/doctor.py
```

On Windows:

```powershell
python .\scripts\doctor.py
```

See [`docs/interactive-input.md`](docs/interactive-input.md) for details.

## Current plugin structure

```text
codex-conductor/
├── plugin.json
├── hooks/
│   ├── hooks.json
│   └── conductor.py
├── scripts/
│   ├── bootstrap.py
│   └── doctor.py
├── docs/
│   ├── interactive-input.md
│   ├── live-test.md
│   └── state-schema.md
├── tests/
│   └── test_conductor.py
└── .agents/plugins/
    └── marketplace.json
```

## Lifecycle hooks

Conductor currently uses:

- `SessionStart` — inject a compact persistent project snapshot.
- `UserPromptSubmit` — automatically initialize minimal state for the first meaningful prompt in a Git repository, then synchronize task/decision context.
- `PreToolUse` — reject `request_user_input_async` in tracked projects, block workers while decisions are unresolved, and enforce the single-worker slot.
- `SubagentStart` — inject the worker contract and prohibit nested agents/project-state edits.
- `SubagentStop` — route worker results or user questions back into the root flow and preserve a waiting worker for later resume.
- `Stop` — block the turn from finishing while an ordinary unresolved blocking decision still needs to be asked/resolved.

## Automatic project initialization

You do not need to run a setup command just to start using Conductor.

On the first meaningful prompt inside a Git repository, Conductor creates:

```text
.conductor/
├── project.json
├── state.json
├── tasks.json
├── decisions.json
└── config.json
```

The initial project profile is intentionally minimal (`kind: generic`, `profile_state: incomplete`). A later `project-setup` skill can enrich it with language, framework, build system, supported versions, and other project-specific information.

Simple conversation such as `Hallo`, `Danke`, or `OK` does not initialize project state.

## Blocking decision gates

Conductor treats product decisions, preferences, requirement gaps, approvals, and scope choices as **blocking decisions** when dependent work would otherwise require guessing.

Expected flow:

```text
work reaches an unresolved choice
        ↓
record .conductor decision
        ↓
mark dependent task waiting_for_user / blocked
        ↓
request_user_input (synchronous)
        ↓
user answers in the root session
        ↓
persist answer + optional extra context
        ↓
unblock satisfied tasks
        ↓
continue work
```

`request_user_input_async` is deliberately denied inside tracked Conductor projects so Codex cannot ask a blocking question and continue implementation at the same time.

When `request_user_input` is available, Conductor expects Codex to invoke the tool rather than printing equivalent options as ordinary assistant text.

### Question layout

For interactive blocking questions, the policy is:

- at most **two substantive questions** per `request_user_input` call;
- **2-3 mutually exclusive options** per substantive question;
- recommended choice first, labeled with `(Recommended)`;
- Codex's built-in free-form `Other` field remains available;
- when possible, the **third tab is reserved for additional context** so the user can add details that were not covered by the choices.

If synchronous `request_user_input` is genuinely unavailable, the root session asks in normal chat, marks the decision `waiting_for_user_external`, ends the turn, and waits. Dependent work must still not continue.

## Worker question handoff

A worker must stop at a safe boundary when it needs a user decision and return `CONDUCTOR_USER_QUESTION` in its handoff.

The root session then:

1. creates/updates the blocking decision,
2. asks the user synchronously,
3. stores the answer,
4. and resumes the same worker with `followup_task` when keeping its context is useful.

The user should never need to switch into the worker conversation.

## Project state

See [`docs/state-schema.md`](docs/state-schema.md) for the v1 contract.

The root session owns `.conductor/`. Workers are instructed not to edit it.

## Manual bootstrap

Automatic initialization is the normal path. The manual helper remains useful for tests or pre-creating a profile:

```bash
python3 scripts/bootstrap.py --name GearMastery --kind minecraft-plugin
```

## Local development / installation

The repository includes a repo marketplace definition under `.agents/plugins/marketplace.json`.

Add the marketplace from the current development branch:

```bash
codex plugin marketplace add s3tupw1zard/codex-conductor --ref feat/initial-conductor-runtime
```

Then install:

```bash
codex plugin add codex-conductor@codex-conductor
```

Plugin hooks are not trusted automatically. Review `hooks/hooks.json` and `hooks/conductor.py` before approving them.

## Tests

No third-party Python packages are required.

```bash
python3 -m unittest discover -s tests -v
```

Current unit coverage includes:

- minimal state creation,
- trivial-prompt handling,
- project snapshots,
- blocking decisions,
- denial of asynchronous project questions,
- Stop-hook blocking,
- external wait fallback,
- and the worker runtime lock.

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

`0.1.2` is still a live-test scaffold. Before treating it as stable, it needs real Codex validation for:

- automatic `.conductor/` creation on Windows and Linux,
- native `request_user_input` menus in normal Default mode with the feature flag enabled,
- synchronous blocking behavior,
- the additional-context tab UX,
- exact agent-tool matcher behavior,
- explicit per-worker model selection,
- worker resume via `followup_task`,
- worker-question handoff,
- stale worker-lock recovery,
- and ChatGPT Work/local-runtime differences for command hooks.
