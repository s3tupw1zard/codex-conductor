#!/usr/bin/env python3
from __future__ import annotations

import json

POLICY = """Codex Conductor interactive decision rule:
- When a blocking product/requirement/user decision must be asked and the `request_user_input` tool is available in this session, you MUST invoke `request_user_input`.
- Do not render the options as ordinary assistant prose when the native tool is available.
- The native call must contain 1-3 questions; prefer no more than two substantive decisions plus one `additional_context` question.
- Each substantive question must provide 2-3 mutually exclusive options, recommended option first, and must not add an explicit Other option because the client provides free-form Other automatically.
- After invoking the synchronous tool, wait for its result. Do not continue dependent work in parallel.
- Plain-text fallback is allowed only when `request_user_input` is genuinely absent/unavailable in the active Codex mode. In that fallback, end the turn and wait for the user's normal reply.
"""


def main() -> int:
    print(json.dumps({
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": POLICY,
        },
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
