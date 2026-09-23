#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR_NAME = ".conductor"
RUNTIME_STALE_SECONDS = 12 * 60 * 60
RESERVATION_STALE_SECONDS = 5 * 60
BLOCKING_DECISION_STATUSES = {"open", "pending", "waiting_for_user", "waiting_for_user_external"}
AGENT_TOOL_NAMES = {"spawn_agent", "followup_task", "Agent"}

ROOT_POLICY = """Codex Conductor is active.

Root-session rules:
- Keep this root session as the user's only conversational interface.
- Treat .conductor/ as the durable project-state source of truth.
- For meaningful project work, keep tasks, dependencies, decisions, and phase state synchronized.
- Do not create task records for trivial conversation or tiny edits that do not benefit from tracking.
- Prefer straightforward, low-risk work directly in the root session.
- Use at most one worker subagent at a time. Workers must never spawn child agents.
- Prefer gpt-5.6-terra for medium worker tasks and gpt-5.6-sol for complex/high-risk design, debugging, or semantic verification when explicit worker model selection is available.
- Never delegate user-facing conversation to a worker.
- The root session owns all .conductor/ state updates and integration of worker results.

Blocking decision gates:
- Never guess a product decision, preference, requirement, approval, or scope choice that can change the result.
- As soon as such a missing decision becomes relevant, stop dependent implementation work at a safe boundary.
- Before asking the user, persist a blocking decision in .conductor/decisions.json and mark dependent/current tasks waiting_for_user or blocked as appropriate.
- Use the synchronous request_user_input tool for blocking decisions. Do NOT use request_user_input_async for blocking decisions.
- request_user_input must actually wait for the answer before dependent work continues.
- Batch no more than two substantive blocking questions in one request_user_input call. When there is room, reserve the final tab for additional user context.
- For each substantive question provide 2-3 mutually exclusive options. Put the best default first and suffix its label with '(Recommended)'. The client adds a free-form Other option automatically; do not add an Other option yourself.
- The additional-context tab should use id 'additional_context', a short header such as 'Zusatz' in the user's language, and explain that the free-form Other field can contain anything else the user wants considered. Offer 'Keine weiteren Angaben (Recommended)' plus one sensible defer/follow-up option.
- After the user answers, persist the answer and any extra context, resolve the decision, unblock only the tasks whose dependencies are now satisfied, then continue.
- If request_user_input is unavailable, ask the blocking question in the root chat, mark the decision waiting_for_user_external, end the turn, and wait for the next user message. Do not continue dependent work.
- If a worker returns CONDUCTOR_USER_QUESTION or waiting_for_user, surface that question through the same blocking decision flow in the root session and resume the same worker when useful.
"""

WORKER_POLICY = """You are the single Codex Conductor worker for one bounded task delegated by the root session.

Worker rules:
- Work only on the assigned task and necessary technical prerequisites.
- Do not spawn or resume any other subagent.
- Do not edit files under .conductor/.
- Do not make product, preference, scope, or approval decisions for the user.
- Technical implementation decisions inside already-approved scope are allowed; report important ones to the root.
- If user input is required, stop at a safe boundary and include CONDUCTOR_USER_QUESTION in the handoff. Do not keep implementing work that depends on that answer.
- Do not ask the user to switch to this worker.
- Keep the handoff compact and structured.

Use this final-response shape whenever practical:

CONDUCTOR_RESULT
status: completed | waiting_for_user | blocked | failed
summary: <short summary>
artifacts:
  - <created or modified path, if any>
decisions:
  - <technical decision, if any>
questions:
  - CONDUCTOR_USER_QUESTION: <question requiring user input, if any>
follow_up:
  - <recommended next task, if any>
verification:
  - <checks performed and result>
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value) or "unknown"


def git_root(cwd: str) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        path = result.stdout.strip()
        return Path(path).resolve() if path else None
    except (OSError, subprocess.SubprocessError):
        return None


def project_root(cwd: str) -> Path:
    root = git_root(cwd)
    if root:
        return root
    current = Path(cwd).resolve()
    for candidate in (current, *current.parents):
        if (candidate / STATE_DIR_NAME).is_dir():
            return candidate
    return current


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def state_dir(root: Path) -> Path:
    return root / STATE_DIR_NAME


def is_trivial_prompt(prompt: str) -> bool:
    text = " ".join(prompt.strip().lower().split())
    if not text:
        return True
    trivial = {
        "hi", "hallo", "hello", "hey", "danke", "thanks", "thank you", "ok", "okay",
        "passt", "alles klar", "weiter", "continue",
    }
    return text in trivial


def should_auto_initialize(root: Path, prompt: str) -> bool:
    return not state_dir(root).exists() and not is_trivial_prompt(prompt) and git_root(str(root)) is not None


def ensure_minimal_state(root: Path) -> bool:
    directory = state_dir(root)
    if directory.exists():
        return False
    timestamp = now_iso()
    directory.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        directory / "project.json",
        {
            "schema_version": 1,
            "name": root.name or "project",
            "kind": "generic",
            "profile_state": "incomplete",
            "technologies": [],
            "frameworks": [],
            "constraints": [],
            "initialized_by": "codex-conductor-auto",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )
    write_json_atomic(
        directory / "state.json",
        {
            "schema_version": 1,
            "phase": "discovery",
            "current_task_id": None,
            "last_completed_task_id": None,
            "selection_gate": None,
            "updated_at": timestamp,
        },
    )
    write_json_atomic(directory / "tasks.json", {"schema_version": 1, "tasks": []})
    write_json_atomic(directory / "decisions.json", {"schema_version": 1, "decisions": []})
    write_json_atomic(
        directory / "config.json",
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
    return True


def normalize_collection(value: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        nested = value.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    return []


def blocking_decisions(root: Path) -> list[dict[str, Any]]:
    doc = read_json(state_dir(root) / "decisions.json", {"decisions": []})
    return [
        item
        for item in normalize_collection(doc, "decisions")
        if item.get("blocking", True) is not False
        and str(item.get("status", "open")) in BLOCKING_DECISION_STATUSES
    ]


def stop_blocking_decisions(root: Path) -> list[dict[str, Any]]:
    return [
        item
        for item in blocking_decisions(root)
        if str(item.get("status", "open")) != "waiting_for_user_external"
    ]


def project_snapshot(root: Path) -> str:
    directory = state_dir(root)
    if not directory.is_dir():
        return (
            f"Project root: {root}\n"
            "Conductor state: not initialized (.conductor/ is absent).\n"
            "A minimal state will be created automatically on the first meaningful prompt inside a Git repository."
        )

    project = read_json(directory / "project.json", {})
    state = read_json(directory / "state.json", {})
    tasks_doc = read_json(directory / "tasks.json", {"tasks": []})
    decisions_doc = read_json(directory / "decisions.json", {"decisions": []})

    project_name = project.get("name") if isinstance(project, dict) else None
    project_kind = project.get("kind") if isinstance(project, dict) else None
    profile_state = project.get("profile_state") if isinstance(project, dict) else None
    phase = state.get("phase") if isinstance(state, dict) else None
    current_task_id = state.get("current_task_id") if isinstance(state, dict) else None
    selection_gate = state.get("selection_gate") if isinstance(state, dict) else None

    tasks = normalize_collection(tasks_doc, "tasks")
    decisions = normalize_collection(decisions_doc, "decisions")
    counts: dict[str, int] = {}
    active_tasks: list[str] = []
    ready_tasks: list[str] = []
    blocked_tasks: list[str] = []

    for task in tasks:
        status = str(task.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
        label = f"{task.get('id', '?')}: {task.get('title', '(untitled)')}"
        if status in {"in_progress", "waiting_for_user"}:
            active_tasks.append(label)
        elif status == "ready":
            ready_tasks.append(label)
        elif status == "blocked":
            blocked_tasks.append(label)

    open_decisions = [
        f"{d.get('id', '?')}: {d.get('question', d.get('title', '(untitled)'))}"
        for d in decisions
        if d.get("blocking", True) is not False and str(d.get("status", "open")) in BLOCKING_DECISION_STATUSES
    ]

    lines = [
        f"Project root: {root}",
        f"Project: {project_name or '(unnamed)'}" + (f" [{project_kind}]" if project_kind else ""),
        f"Project profile: {profile_state or '(unset)'}",
        f"Phase: {phase or '(unset)'}",
        f"Current task: {current_task_id or '(none)'}",
    ]
    if counts:
        lines.append("Task counts: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    if active_tasks:
        lines.append("Active tasks: " + "; ".join(active_tasks[:5]))
    if ready_tasks:
        lines.append("Ready tasks: " + "; ".join(ready_tasks[:5]))
    if blocked_tasks:
        lines.append("Blocked tasks: " + "; ".join(blocked_tasks[:5]))
    if open_decisions:
        lines.append("BLOCKING user decisions: " + "; ".join(open_decisions[:5]))
    if selection_gate:
        lines.append("Selection gate: " + json.dumps(selection_gate, ensure_ascii=False))
    return "\n".join(lines)


def plugin_data_dir() -> Path:
    configured = os.environ.get("PLUGIN_DATA")
    path = Path(configured) if configured else Path(tempfile.gettempdir()) / "codex-conductor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_file(session_id: str) -> Path:
    runtime = plugin_data_dir() / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime / f"{safe_id(session_id)}.json"


def read_runtime(session_id: str) -> dict[str, Any]:
    path = runtime_file(session_id)
    data = read_json(path, {})
    if not isinstance(data, dict):
        return {}
    updated_at = data.get("updated_at")
    state = data.get("state")
    stale_after = RESERVATION_STALE_SECONDS if state == "reserved" else RUNTIME_STALE_SECONDS
    if isinstance(updated_at, (int, float)) and time.time() - float(updated_at) > stale_after:
        try:
            path.unlink()
        except OSError:
            pass
        return {}
    return data


def write_runtime(session_id: str, data: dict[str, Any]) -> None:
    payload = dict(data)
    payload["updated_at"] = int(time.time())
    write_json_atomic(runtime_file(session_id), payload)


def clear_runtime(session_id: str, agent_id: str | None = None) -> None:
    path = runtime_file(session_id)
    if not path.exists():
        return
    if agent_id:
        current = read_json(path, {})
        if isinstance(current, dict) and current.get("agent_id") not in {None, agent_id}:
            return
    try:
        path.unlink()
    except OSError:
        pass


def context_output(event_name: str, additional_context: str, system_message: str | None = None) -> None:
    payload: dict[str, Any] = {
        "continue": True,
        "hookSpecificOutput": {"hookEventName": event_name, "additionalContext": additional_context},
    }
    if system_message:
        payload["systemMessage"] = system_message
    print(json.dumps(payload, ensure_ascii=False))


def deny_tool(event_name: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def handle_session_start(event: dict[str, Any]) -> None:
    root = project_root(str(event.get("cwd") or os.getcwd()))
    context_output(
        "SessionStart",
        ROOT_POLICY
        + "\nSession source: " + str(event.get("source", "unknown"))
        + "\n\nPersistent project snapshot:\n" + project_snapshot(root),
    )


def handle_prompt_submit(event: dict[str, Any]) -> None:
    root = project_root(str(event.get("cwd") or os.getcwd()))
    prompt = str(event.get("prompt") or "")
    initialized = False
    if should_auto_initialize(root, prompt):
        initialized = ensure_minimal_state(root)

    open_decisions = blocking_decisions(root) if state_dir(root).exists() else []
    extra = """
For this user prompt:
- First classify it as conversational/trivial, tracked project work, or a response to an open Conductor decision.
- If it is tracked project work, maintain the minimum useful dependency-aware task graph before or alongside execution.
- Do not invent dependencies merely to create a larger graph.
- If a missing user/product decision becomes relevant, record it immediately and enter the blocking decision-gate flow before dependent implementation continues.
- If the prompt answers an existing blocking decision, resolve that decision first, persist the answer/additional context, unblock satisfied tasks, and only then resume work.
- If a worker is warranted, delegate one bounded task only and keep integration/user questions in the root.
"""
    if open_decisions:
        extra += (
            "\nThere are unresolved blocking decisions. Treat this prompt first as a possible answer to them. "
            "Do not start unrelated or dependent implementation until they are resolved."
        )
    message = "Initialized minimal .conductor project state automatically." if initialized else None
    context_output(
        "UserPromptSubmit",
        ROOT_POLICY + extra + "\nPersistent project snapshot:\n" + project_snapshot(root),
        system_message=message,
    )


def reserve_or_guard_tool(event: dict[str, Any]) -> None:
    root = project_root(str(event.get("cwd") or os.getcwd()))
    tool_name = str(event.get("tool_name") or "")

    if tool_name == "request_user_input_async" and state_dir(root).exists():
        deny_tool(
            "PreToolUse",
            "Codex Conductor disables asynchronous user questions inside tracked projects. "
            "For a blocking product/requirement decision, persist the decision and use synchronous request_user_input so work waits for the answer. "
            "For non-blocking information, continue without asking or ask later in a normal turn.",
        )
        return

    unresolved = blocking_decisions(root) if state_dir(root).exists() else []
    if tool_name in AGENT_TOOL_NAMES and unresolved:
        ids = ", ".join(str(item.get("id", "?")) for item in unresolved[:5])
        deny_tool(
            "PreToolUse",
            f"Resolve blocking Conductor decision(s) {ids} before spawning or resuming a worker. "
            "Use synchronous request_user_input in the root session.",
        )
        return

    if tool_name not in AGENT_TOOL_NAMES:
        return

    session_id = str(event.get("session_id") or "unknown")
    current = read_runtime(session_id)
    if current.get("state") in {"reserved", "active"}:
        deny_tool(
            "PreToolUse",
            "Codex Conductor allows only one active worker at a time. Wait for the current worker to stop or resume that same worker after it becomes idle.",
        )
        return
    if current.get("state") == "waiting_for_user" and tool_name != "followup_task":
        deny_tool(
            "PreToolUse",
            "A previous Conductor worker is waiting on a user decision. Resolve it in the root session, then resume the same worker with followup_task when useful.",
        )
        return

    write_runtime(session_id, {
        "state": "reserved",
        "tool_name": tool_name,
        "turn_id": event.get("turn_id"),
        "tool_use_id": event.get("tool_use_id"),
        "previous_agent_id": current.get("agent_id") if current else None,
    })


def handle_subagent_start(event: dict[str, Any]) -> None:
    session_id = str(event.get("session_id") or "unknown")
    agent_id = str(event.get("agent_id") or "unknown")
    current = read_runtime(session_id)
    violation = current.get("state") == "active" and current.get("agent_id") not in {None, agent_id}
    write_runtime(session_id, {
        "state": "active",
        "agent_id": agent_id,
        "agent_type": str(event.get("agent_type") or "unknown"),
        "turn_id": event.get("turn_id"),
        "model": event.get("model"),
    })
    context = WORKER_POLICY
    if violation:
        context = (
            "CONDUCTOR POLICY VIOLATION: another worker was already active. Do not perform project work. "
            "Return immediately with status=blocked.\n\n" + context
        )
    context_output("SubagentStart", context)


def handle_subagent_stop(event: dict[str, Any]) -> None:
    session_id = str(event.get("session_id") or "unknown")
    agent_id = str(event.get("agent_id") or "unknown")
    last_message = str(event.get("last_assistant_message") or "")
    lowered = last_message.lower()
    needs_user = "conductor_user_question" in lowered or "waiting_for_user" in lowered

    if needs_user:
        write_runtime(session_id, {
            "state": "waiting_for_user",
            "agent_id": agent_id,
            "agent_type": str(event.get("agent_type") or "unknown"),
            "turn_id": event.get("turn_id"),
            "model": event.get("model"),
        })
        context = (
            "The worker stopped because user input is required. Immediately convert the worker question into a blocking .conductor decision, "
            "mark dependent work waiting_for_user, and ask it in the root session with synchronous request_user_input. "
            "Do not continue dependent implementation. After the answer is persisted, prefer followup_task on this same worker when its context is useful."
        )
    else:
        clear_runtime(session_id, agent_id=agent_id)
        context = (
            "The worker has stopped. Integrate its result in the root session, verify as needed, and update .conductor task/state records. "
            "Do not expose internal worker mechanics unless useful to the user."
        )
    context_output("SubagentStop", context)


def handle_stop(event: dict[str, Any]) -> None:
    root = project_root(str(event.get("cwd") or os.getcwd()))
    unresolved = stop_blocking_decisions(root) if state_dir(root).exists() else []
    if unresolved:
        ids = ", ".join(str(item.get("id", "?")) for item in unresolved[:5])
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"Blocking Conductor decision(s) {ids} are unresolved. Do not finish or continue dependent work. "
                "Ask them now with synchronous request_user_input, using at most two substantive questions plus an additional-context tab, then persist the answers."
            ),
        }, ensure_ascii=False))
        return
    print(json.dumps({"continue": True}))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: conductor.py <session-start|prompt-submit|pre-tool|subagent-start|subagent-stop|stop>", file=sys.stderr)
        return 2
    handlers = {
        "session-start": handle_session_start,
        "prompt-submit": handle_prompt_submit,
        "pre-tool": reserve_or_guard_tool,
        "subagent-start": handle_subagent_start,
        "subagent-stop": handle_subagent_stop,
        "stop": handle_stop,
    }
    handler = handlers.get(sys.argv[1])
    if handler is None:
        print(f"unknown action: {sys.argv[1]}", file=sys.stderr)
        return 2
    event = read_stdin_json()
    try:
        handler(event)
        return 0
    except Exception as exc:
        print(f"Codex Conductor hook error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
