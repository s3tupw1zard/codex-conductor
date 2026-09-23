#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

STATE_DIR_NAME = ".conductor"
RUNTIME_STALE_SECONDS = 12 * 60 * 60
RESERVATION_STALE_SECONDS = 5 * 60

ROOT_POLICY = """Codex Conductor is active.

Root-session rules:
- Keep this root session as the user's only conversational interface.
- Treat .conductor/ as the persistent project-state source when it exists.
- For meaningful project work, keep tasks, dependencies, decisions, and phase state synchronized.
- Do not create task records for trivial conversational requests or tiny edits that do not benefit from tracking.
- Prefer doing straightforward, low-risk work directly in the root session.
- Use at most one worker subagent at a time.
- A worker is appropriate when a bounded task materially benefits from a stronger model or isolated focus.
- Prefer gpt-5.6-terra for medium-complexity worker tasks and gpt-5.6-sol for high-complexity, high-risk, architecture, difficult debugging, or semantic verification tasks when explicit worker model selection is available.
- Never delegate user-facing conversation to the worker.
- If a worker needs a product decision, requirement clarification, approval, or other user input, surface the question in this root session. Do not ask the user to switch to a subagent.
- Resume the same worker after the user answers when its context is still useful.
- Workers must not spawn child agents and must not modify .conductor/ state directly.
- The root session owns integration of worker results and persistent project-state updates.
"""

WORKER_POLICY = """You are the single Codex Conductor worker for a bounded task delegated by the root session.

Worker rules:
- Work only on the assigned task and its necessary technical prerequisites.
- Do not spawn or resume any other subagent.
- Do not edit files under .conductor/.
- Do not make product decisions, user-preference decisions, scope choices, or approval decisions on the user's behalf.
- Technical implementation decisions inside already-approved scope are allowed; report important ones to the root.
- If user input is required, stop at a safe boundary and include a CONDUCTOR_USER_QUESTION entry in your handoff. The root session will ask the user and may resume you afterward.
- Do not tell the user to open or switch to this worker.
- Keep the final handoff compact and structured.

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


def state_dir(root: Path) -> Path:
    return root / STATE_DIR_NAME


def plugin_data_dir() -> Path:
    configured = os.environ.get("PLUGIN_DATA")
    if configured:
        path = Path(configured)
    else:
        path = Path(tempfile.gettempdir()) / "codex-conductor"
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
    now = time.time()
    stale_after = RESERVATION_STALE_SECONDS if state == "reserved" else RUNTIME_STALE_SECONDS

    if isinstance(updated_at, (int, float)) and now - float(updated_at) > stale_after:
        try:
            path.unlink()
        except OSError:
            pass
        return {}
    return data


def write_runtime(session_id: str, data: dict[str, Any]) -> None:
    path = runtime_file(session_id)
    payload = dict(data)
    payload["updated_at"] = int(time.time())
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def clear_runtime(session_id: str, agent_id: str | None = None) -> None:
    path = runtime_file(session_id)
    if not path.exists():
        return
    if agent_id:
        current = read_json(path, {})
        if isinstance(current, dict):
            active_id = current.get("agent_id")
            if active_id and active_id != agent_id:
                return
    try:
        path.unlink()
    except OSError:
        pass


def normalize_collection(value: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        nested = value.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    return []


def project_snapshot(root: Path) -> str:
    directory = state_dir(root)
    if not directory.is_dir():
        return (
            f"Project root: {root}\n"
            "Conductor state: not initialized (.conductor/ is absent).\n"
            "Do not initialize it implicitly unless the user or a project-setup workflow requests initialization."
        )

    project = read_json(directory / "project.json", {})
    state = read_json(directory / "state.json", {})
    tasks_doc = read_json(directory / "tasks.json", {"tasks": []})
    decisions_doc = read_json(directory / "decisions.json", {"decisions": []})

    project_name = project.get("name") if isinstance(project, dict) else None
    project_kind = project.get("kind") if isinstance(project, dict) else None
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
        f"{decision.get('id', '?')}: {decision.get('question', decision.get('title', '(untitled)'))}"
        for decision in decisions
        if decision.get("status") in {"open", "pending", "waiting_for_user"}
    ]

    lines = [
        f"Project root: {root}",
        f"Project: {project_name or '(unnamed)'}" + (f" [{project_kind}]" if project_kind else ""),
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
        lines.append("Open decisions: " + "; ".join(open_decisions[:5]))
    if selection_gate:
        lines.append("Selection gate: " + json.dumps(selection_gate, ensure_ascii=False))

    return "\n".join(lines)


def context_output(event_name: str, additional_context: str, system_message: str | None = None) -> None:
    payload: dict[str, Any] = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": additional_context,
        },
    }
    if system_message:
        payload["systemMessage"] = system_message
    print(json.dumps(payload, ensure_ascii=False))


def deny_tool(event_name: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event_name,
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )


def handle_session_start(event: dict[str, Any]) -> None:
    root = project_root(str(event.get("cwd") or os.getcwd()))
    source = event.get("source", "unknown")
    context = (
        ROOT_POLICY
        + "\nSession source: "
        + str(source)
        + "\n\nPersistent project snapshot:\n"
        + project_snapshot(root)
    )
    context_output("SessionStart", context)


def handle_prompt_submit(event: dict[str, Any]) -> None:
    root = project_root(str(event.get("cwd") or os.getcwd()))
    prompt = str(event.get("prompt") or "")
    snapshot = project_snapshot(root)
    extra = """
For this user prompt:
- First classify it as conversational/trivial, tracked project work, or a response to an open Conductor decision.
- If it is tracked project work and .conductor/ exists, update or create the minimum useful task graph with explicit dependencies before or alongside execution.
- Do not invent dependencies merely to create a larger graph.
- If the prompt resolves an open decision, record that resolution in the root-owned project state and resume the relevant work.
- If a worker is warranted, delegate one bounded task only and keep integration/user questions in the root.
"""
    context = ROOT_POLICY + extra + "\nPersistent project snapshot:\n" + snapshot
    if prompt:
        context += "\nCurrent prompt length: " + str(len(prompt)) + " characters."
    context_output("UserPromptSubmit", context)


def reserve_worker(event: dict[str, Any]) -> None:
    session_id = str(event.get("session_id") or "unknown")
    tool_name = str(event.get("tool_name") or "")
    current = read_runtime(session_id)

    if current.get("state") in {"reserved", "active"}:
        deny_tool(
            "PreToolUse",
            "Codex Conductor allows only one active worker at a time. "
            "Wait for the current worker to stop or resume that same worker after it becomes idle.",
        )
        return

    write_runtime(
        session_id,
        {
            "state": "reserved",
            "tool_name": tool_name,
            "turn_id": event.get("turn_id"),
            "tool_use_id": event.get("tool_use_id"),
        },
    )


def handle_subagent_start(event: dict[str, Any]) -> None:
    session_id = str(event.get("session_id") or "unknown")
    agent_id = str(event.get("agent_id") or "unknown")
    agent_type = str(event.get("agent_type") or "unknown")
    current = read_runtime(session_id)

    violation = (
        current.get("state") == "active"
        and current.get("agent_id")
        and current.get("agent_id") != agent_id
    )

    write_runtime(
        session_id,
        {
            "state": "active",
            "agent_id": agent_id,
            "agent_type": agent_type,
            "turn_id": event.get("turn_id"),
            "model": event.get("model"),
        },
    )

    context = WORKER_POLICY
    if violation:
        context = (
            "CONDUCTOR POLICY VIOLATION: another worker was already active. "
            "Do not perform project work. Return immediately with status=blocked and explain that "
            "the root must wait for the existing worker.\n\n"
            + context
        )
    context_output("SubagentStart", context)


def handle_subagent_stop(event: dict[str, Any]) -> None:
    session_id = str(event.get("session_id") or "unknown")
    agent_id = str(event.get("agent_id") or "unknown")
    last_message = str(event.get("last_assistant_message") or "")
    clear_runtime(session_id, agent_id=agent_id)

    lowered = last_message.lower()
    needs_user = "conductor_user_question" in lowered or "waiting_for_user" in lowered

    if needs_user:
        context = (
            "The worker stopped because user input appears to be required. "
            "Surface the worker's question in the root session now. Do not guess the answer and do not ask "
            "the user to switch to the worker. After the user answers, prefer followup_task on the same worker "
            "when preserving its context is useful. Update .conductor/ decision/task state from the root."
        )
    else:
        context = (
            "The worker has stopped. Integrate its result in the root session, perform any necessary root-level "
            "verification, and update .conductor/ task/state records if this was tracked project work. "
            "Do not expose internal worker mechanics unless useful to the user."
        )

    context_output("SubagentStop", context)


def handle_stop(event: dict[str, Any]) -> None:
    # Stop hooks require JSON on stdout. We deliberately do not force an extra turn.
    print(json.dumps({"continue": True}))


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: conductor.py <session-start|prompt-submit|pre-agent|subagent-start|subagent-stop|stop>",
            file=sys.stderr,
        )
        return 2

    action = sys.argv[1]
    event = read_stdin_json()

    handlers = {
        "session-start": handle_session_start,
        "prompt-submit": handle_prompt_submit,
        "pre-agent": reserve_worker,
        "subagent-start": handle_subagent_start,
        "subagent-stop": handle_subagent_stop,
        "stop": handle_stop,
    }

    handler = handlers.get(action)
    if handler is None:
        print(f"unknown action: {action}", file=sys.stderr)
        return 2

    try:
        handler(event)
        return 0
    except Exception as exc:  # Hooks should fail open rather than break Codex.
        print(f"Codex Conductor hook error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
