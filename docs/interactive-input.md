# Interactive blocking-decision UI

Codex Conductor expects blocking product/requirement decisions to use Codex's synchronous `request_user_input` tool whenever that tool is available.

This matters because plain assistant text can only print options. `request_user_input` creates the native interactive selection UI, waits for the answer, supports 1-3 questions, and automatically adds a free-form `Other` answer path.

## Normal Codex / Default mode

As of the current Codex build, `request_user_input` in the normal **Default** collaboration mode is guarded by the Codex feature flag:

```toml
[features]
plugins = true
default_mode_request_user_input = true
```

The upstream Codex feature is currently not enabled by default. Restart Codex after changing `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`).

Run Conductor's setup check with:

```bash
python scripts/doctor.py
```

On Windows:

```powershell
python .\scripts\doctor.py
```

## Plan mode

Codex also exposes `request_user_input` in collaboration modes that inherently allow it, including Plan mode. Conductor does not require Plan mode when `default_mode_request_user_input = true` is enabled.

## Conductor behavior

For a blocking decision:

1. Persist the decision in `.conductor/decisions.json`.
2. Mark dependent work as `waiting_for_user` or `blocked`.
3. If the `request_user_input` tool is available, **invoke that tool**. Do not print the same options as a normal assistant response instead.
4. Ask at most two substantive questions per call and reserve a third question for additional context when useful.
5. Each substantive question should contain 2-3 mutually exclusive options; put the recommended choice first.
6. Do not add an explicit `Other` option. Codex adds the free-form Other path automatically.
7. Do not continue dependent work until the synchronous result has been returned and persisted.

If `request_user_input` is genuinely unavailable in the active host/mode, Conductor falls back to a normal root-session question and must end the turn while waiting. The fallback is intentionally non-interactive; it must never be used merely because the model chose not to call an available `request_user_input` tool.

The plugin also injects a dedicated `UserPromptSubmit` policy hook whose only purpose is to reinforce this rule separately from the broader Conductor orchestration policy.

## Desired layout

With two substantive decisions, Conductor should aim for three tabs/questions:

```text
[ Entscheidung 1 ] [ Entscheidung 2 ] [ Zusatz ]
```

The `Zusatz` question should offer a no-extra-context default while allowing the native free-form Other field to contain arbitrary additional requirements, ideas, or constraints.
