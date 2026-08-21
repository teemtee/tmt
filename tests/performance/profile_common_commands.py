#!/usr/bin/env python3
"""
Collect cProfile data for common metadata-heavy tmt commands.

Point ``REPO`` at the tmt git tree, edit ``COMMANDS`` if needed, then run::

    python3 tests/performance/profile_common_commands.py

Writes ``.prof`` files to ``PROFILE_DIR``. Hotspot tables and other analysis live
in ``summarize_profiles.py`` (common-commands preset at the top of that file).
"""

from __future__ import annotations

import sys
from pathlib import Path

from profile_lib import build_subprocess_env, profile_safe_name, run_cprofile

# Standalone script: do not import tmt (see pyproject.toml TID251 for tests/performance/*).

REPO = Path.cwd()
WORK_DIR = REPO
PYTHON = sys.executable
PROFILE_DIR = REPO / ".profile_common_commands"

# label, arguments passed to ``python -m tmt`` (after the cProfile wrapper).
COMMANDS: list[tuple[str, list[str]]] = [
    ("tests ls", ["tests", "ls"]),
    ("plans ls", ["plans", "ls"]),
    ("stories ls", ["stories", "ls"]),
    ("tests show (1 test)", ["tests", "show", "/tests/provision/virtual/dependencies"]),
    (
        "run discover (core)",
        ["run", "discover", "plan", "-n", "^/plans/features/core$"],
    ),
    ("lint", ["lint"]),
]


def main() -> int:
    repo = REPO.resolve()
    work_dir = WORK_DIR.resolve()
    profile_dir = PROFILE_DIR.resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    env = build_subprocess_env(repo)

    print(f"Repository: {repo}", file=sys.stderr)
    print(f"Work directory: {work_dir}", file=sys.stderr)
    print(f"Python: {PYTHON}", file=sys.stderr)
    print(f"Profile directory: {profile_dir}", file=sys.stderr)

    for label, args in COMMANDS:
        prof_path = profile_dir / f"{profile_safe_name(label)}.prof"
        print(f"Profiling {label}...", file=sys.stderr)
        completed = run_cprofile(PYTHON, work_dir, env, args, prof_path)
        if completed.returncode != 0:
            print(f"Warning: {label} exited {completed.returncode}", file=sys.stderr)
        print(f"  -> {prof_path}", file=sys.stderr)

    print(
        "\nDone. Run: python3 tests/performance/summarize_profiles.py",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
