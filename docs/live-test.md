# Live test procedure

This checklist validates the behavior that matters before Codex Conductor can be treated as a usable v0.1 runtime.

## Refresh an installed development build

When testing the development branch after changes:

```bash
codex plugin marketplace upgrade codex-conductor
codex plugin add codex-conductor@codex-conductor
```

Restart Codex after reinstalling so `SessionStart` and the refreshed hook bundle are loaded.

The current development build is `0.1.3`.

## Enable native interactive input in Default mode

Conductor's blocking-decision UX depends on Codex's synchronous `request_user_input` tool. In the normal **Default** collaboration mode, current Codex builds require this host feature flag:

```toml
[features]
plugins = true
default_mode_request_user_input = true
```

After editing `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`), restart Codex.

Verify the setup with:

```powershell
python .\scripts\doctor.py
```

Expected: both checks report `PASS`.

Without this upstream Codex feature flag, Conductor can still pause and wait, but Default mode cannot expose the native interactive selection UI; the only safe fallback is a plain-text root-session question.

## Windows hook support

`hooks/hooks.json` declares both:

- `command` using `python3` for Unix-like systems;
- `commandWindows` using `python` and `%PLUGIN_ROOT%` for Windows.

## Test 1 — automatic project state

Use an empty Git repository and send a meaningful project prompt.

After the first prompt, verify that the repository contains:

```text
.conductor/
├── project.json
├── state.json
├── tasks.json
├── decisions.json
└── config.json
```

A greeting or simple `Danke` must not initialize the directory.

## Test 2 — root-owned blocking decision gate

Use a prompt with a deliberately unresolved product decision.

Expected behavior:

1. Conductor persists a blocking entry in `.conductor/decisions.json` before dependent implementation proceeds.
2. The relevant task becomes `waiting_for_user` or dependent tasks become `blocked`.
3. If `request_user_input` is available, the **root session** invokes the tool rather than printing equivalent options as normal assistant text.
4. Codex uses synchronous `request_user_input` rather than `request_user_input_async`.
5. The root session waits for the answer; dependent implementation does not continue in the background.
6. After the answer, the decision becomes `resolved`, the answer is stored, and only satisfied tasks are unblocked.

If Codex prints a numbered list of choices as ordinary assistant prose while the native tool is available, treat the interaction test as failed.

## Test 3 — question UX

For one or two substantive blocking questions, the interactive request should provide:

- 2-3 mutually exclusive suggestions per question;
- the recommended option first with `(Recommended)` in its label;
- the client's free-form `Other` input for a custom answer;
- when possible, a final `Zusatz` / additional-context tab.

## Test 4 — fallback when synchronous input is genuinely unavailable

If the current host/mode genuinely does not expose synchronous `request_user_input`, Codex must:

1. mark the decision `waiting_for_user_external`;
2. ask the question in the root chat;
3. end the turn;
4. wait for the next user message;
5. not continue dependent work meanwhile.

## Test 5 — worker handoff

Use a bounded task complex enough to justify a worker and include a product decision that becomes relevant only after the worker has started.

Expected behavior:

- at most one worker is active;
- the worker never spawns a child agent;
- the worker is **not allowed to call `request_user_input` or `request_user_input_async`**;
- if the worker attempts such a tool call, Conductor blocks it using the subagent `agent_id`/`agent_type` supplied by Codex;
- the worker instead returns `CONDUCTOR_USER_QUESTION` and stops at a safe boundary;
- the root converts the question into a blocking decision and opens native `request_user_input`;
- the interactive question should appear directly on the root surface; the user should not need to reveal a worker view with Alt+Up;
- after resolution, the root prefers resuming the same worker with `followup_task` when retaining its context is useful.

Needing to switch/reveal a worker surface to answer the question is a failed handoff test.

## Test 6 — resume

Close Codex completely, reopen the same repository, and ask:

> Wo stehen wir gerade?

The new root session should receive the persistent project snapshot from `SessionStart`, including the current phase, active/ready/blocked tasks, and unresolved decisions.
