#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Any

USER_INPUT_TOOLS = {"request_user_input", "request_user_input_async"}


def read_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def block_reason(event: dict[str, Any]) -> str | None:
    tool_name = str(event.get("tool_name") or "")
    if tool_name not in USER_INPUT_TOOLS:
        return None

    # Codex serializes agent_id / agent_type into PreToolUse stdin for
    # thread-spawned subagents. Root-session tool calls leave them null/absent.
    agent_id = event.get("agent_id")
    agent_type = event.get("agent_type")
    if not agent_id and not agent_type:
        return None

    return (
        "Codex Conductor workers must never ask the user directly. "
        "Do not call request_user_input or request_user_input_async from this subagent. "
        "Stop at a safe boundary and return status=waiting_for_user with a structured "
        "CONDUCTOR_USER_QUESTION in the worker handoff. The root session will persist the "
        "decision, show the native interactive request_user_input UI to the user, collect the "
        "answer, and resume this same worker with followup_task when useful."
    )


def main() -> int:
    reason = block_reason(read_event())
    if reason is None:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
