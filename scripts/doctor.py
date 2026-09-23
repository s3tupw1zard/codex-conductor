#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def load_features(config_path: Path) -> dict[str, bool]:
    try:
        raw = config_path.read_bytes()
    except OSError:
        return {}

    try:
        import tomllib

        document = tomllib.loads(raw.decode("utf-8"))
        features = document.get("features", {})
        if isinstance(features, dict):
            return {
                str(key): value
                for key, value in features.items()
                if isinstance(value, bool)
            }
    except (ImportError, UnicodeDecodeError, ValueError):
        pass

    text = raw.decode("utf-8", errors="replace")
    match = re.search(r"(?ms)^\s*\[features\]\s*$([\s\S]*?)(?=^\s*\[|\Z)", text)
    if not match:
        return {}

    values: dict[str, bool] = {}
    for line in match.group(1).splitlines():
        item = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(true|false)\s*(?:#.*)?$", line, re.I)
        if item:
            values[item.group(1)] = item.group(2).lower() == "true"
    return values


def main() -> int:
    home = codex_home()
    config = home / "config.toml"
    features = load_features(config)

    print("Codex Conductor doctor")
    print(f"Codex home: {home}")
    print(f"Config: {config}")

    if not config.is_file():
        print("WARN config.toml was not found.")
        print("     Interactive blocking menus in Default mode require:")
        print("     [features]")
        print("     default_mode_request_user_input = true")
        return 1

    checks = [
        (
            "plugins",
            "Codex plugins",
            "Required for Codex Conductor itself.",
        ),
        (
            "default_mode_request_user_input",
            "Interactive request_user_input in Default mode",
            "Required for Conductor's selectable blocking-decision UI during normal Codex sessions.",
        ),
    ]

    failed = False
    for key, label, help_text in checks:
        value = features.get(key)
        if value is True:
            print(f"PASS {label}: enabled")
        elif value is False:
            failed = True
            print(f"FAIL {label}: disabled")
            print(f"     {help_text}")
        else:
            failed = True
            print(f"FAIL {label}: not explicitly enabled")
            print(f"     {help_text}")

    if failed:
        print("\nRecommended config:")
        print("[features]")
        print("plugins = true")
        print("default_mode_request_user_input = true")
        print("\nRestart Codex after changing config.toml.")
        return 1

    print("\nPASS Conductor prerequisites for normal Default-mode interactive decisions are enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
