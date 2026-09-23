# Live test procedure

This checklist validates the behavior that matters before Codex Conductor can be treated as a usable v0.1 runtime.

## Refresh an installed development build

When testing the development branch after changes:

```bash
codex plugin marketplace upgrade codex-conductor
codex plugin add codex-conductor@codex-conductor
```

Restart Codex after reinstalling so `SessionStart` and the refreshed hook bundle are loaded.

The current development build is `0.1.2`.

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

This is important because Windows installations commonly expose Python as `python` while Linux commonly exposes it as `python3`.

## Test 1 — automatic project state

Use an empty Git repository and send a meaningful project prompt such as:

> Erstelle eine kleine Python-CLI namens `task-notes`. Sie soll Notizen in einer lokalen JSON-Datei speichern. Benutzer sollen Notizen hinzufügen, auflisten, als erledigt markieren und löschen können. Nutze nur die Python-Standardbibliothek. Bevor du alles implementierst, strukturiere die Arbeit sinnvoll.

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

## Test 2 — blocking decision gate

Use a prompt with a deliberately unresolved product decision:

> Bei der Speicherung bin ich mir noch nicht sicher, ob erledigte Notizen dauerhaft gespeichert oder beim Beenden automatisch entfernt werden sollen. Triff diese Produktentscheidung nicht selbst. Sobald die Entscheidung für die weitere Arbeit nötig ist, frage mich und warte auf meine Antwort.

Expected behavior:

1. Conductor persists a blocking entry in `.conductor/decisions.json` before dependent implementation proceeds.
2. The relevant task becomes `waiting_for_user` or dependent tasks become `blocked`.
3. If `request_user_input` is available, Codex **invokes the tool** rather than printing equivalent options as normal assistant text.
4. Codex uses synchronous `request_user_input` rather than `request_user_input_async`.
5. The root session waits for the answer; dependent implementation does not continue in the background.
6. After the answer, the decision becomes `resolved`, the answer is stored, and only satisfied tasks are unblocked.

If Codex prints a numbered list of choices as ordinary assistant prose while the native `request_user_input` tool is available, treat the interaction test as failed.

## Test 3 — question UX

For one or two substantive blocking questions, the interactive request should provide:

- 2-3 mutually exclusive suggestions per question;
- the recommended option first with `(Recommended)` in its label;
- the client's free-form `Other` input for a custom answer;
- when possible, a final `Zusatz` / additional-context tab.

The additional-context tab should offer `Keine weiteren Angaben (Recommended)` and allow the free-form field to contain anything else the user wants considered.

Conductor intentionally limits one batch to at most two substantive questions so the third tab can be used for extra context.

## Test 4 — fallback when synchronous input is genuinely unavailable

If the current host/mode genuinely does not expose synchronous `request_user_input`, Codex must:

1. mark the decision `waiting_for_user_external`;
2. ask the question in the root chat;
3. end the turn;
4. wait for the next user message;
5. not continue dependent work meanwhile.

The fallback must not be chosen merely because the model preferred prose over an available native tool.

## Test 5 — worker handoff

Use a bounded task complex enough to justify a worker.

Expected behavior:

- at most one worker is active;
- the worker never spawns a child agent;
- if it needs a user/product decision, it returns `CONDUCTOR_USER_QUESTION` and stops at a safe boundary;
- the root converts the question into a blocking decision and asks the user through native `request_user_input` when available;
- after resolution, the root prefers resuming the same worker with `followup_task` when retaining its context is useful;
- the user never needs to switch into the worker conversation.

## Test 6 — resume

Close Codex completely, reopen the same repository, and ask:

> Wo stehen wir gerade?

The new root session should receive the persistent project snapshot from `SessionStart`, including the current phase, active/ready/blocked tasks, and unresolved decisions.
