#!/usr/bin/env python
"""PreToolUse guard: block a git commit that carries an AI trace or fails the ruff+pytest gate."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    command = json.loads(sys.stdin.read()).get("tool_input", {}).get("command", "")
except (ValueError, AttributeError):
    sys.exit(0)

if not re.search(r"git\s+commit\b", command):
    sys.exit(0)

trace = re.search(r"co-authored-by|claude|anthropic|ai-generated|generated with|🤖|noreply@", command, re.I)
if trace:
    sys.stderr.write(
        f"Commit blocked: message carries an AI trace ({trace.group(0)!r}). "
        "History must read as the user's own work; remove it.\n"
    )
    sys.exit(2)

gate = (
    ("ruff check", [str(ROOT / ".venv/Scripts/ruff.exe"), "check", "neko", "planner"]),
    ("ruff format --check", [str(ROOT / ".venv/Scripts/ruff.exe"), "format", "--check", "neko", "planner"]),
    ("pytest", [str(ROOT / ".venv/Scripts/pytest.exe"), "-q"]),
)
for label, argv in gate:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, cwd=ROOT)
    except OSError as exc:
        sys.stderr.write(f"Commit gate could not run {label}: {exc}\n")
        sys.exit(2)
    if result.returncode != 0:
        tail = (result.stdout + result.stderr).strip()[-1500:]
        sys.stderr.write(f"Commit blocked: {label} failed.\n{tail}\n")
        sys.exit(2)
