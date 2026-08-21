#!/usr/bin/env python3
"""
Collect cProfile data for synthetic full tmt runs.

Point ``REPO`` at the tmt git tree, create the synthetic fmf tree with
``create_synthetic_plan.py``, edit matrix settings below, then run::

    python3 tests/performance/profile_synthetic_runs.py

Writes ``.prof`` files to ``SYNTHETIC_RUNS_PROFILE_DIR`` under the repo root.
See ``summarize_profiles.py`` for the synthetic analysis preset.

The default matrix runtime is several hours.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from profile_lib import (
    PERF_DIR,
    SYNTHETIC_DIR,
    SYNTHETIC_RUNS_PROFILE_DIR,
    build_subprocess_env,
    profile_safe_name,
    run_cprofile,
)

# Standalone script: do not import tmt (see pyproject.toml TID251 for tests/performance/*).

REPO = Path.cwd()
WORK_DIR = REPO / SYNTHETIC_DIR
PYTHON = sys.executable

PLANS: tuple[str, ...] = ("true", "write")
PROVISION_METHODS: tuple[str, ...] = ("local", "virtual", "container")
STATE_FORMATS: tuple[str, ...] = ("yaml", "json")

CREATE_SYNTHETIC_SCRIPT = PERF_DIR / "create_synthetic_plan.py"


def synthetic_tree_ready(tests_root: Path) -> bool:
    return (tests_root / "plan.fmf").is_file() and (tests_root / "tests.fmf").is_file()


def require_synthetic_plan(work_dir: Path) -> None:
    if synthetic_tree_ready(work_dir):
        return
    print(f"Warning: synthetic plan not found under {work_dir}", file=sys.stderr)
    raise SystemExit(f"Run first: python3 {CREATE_SYNTHETIC_SCRIPT}")


def iter_run_specs(
    plans: Sequence[str],
    methods: Sequence[str],
    state_formats: Sequence[str],
) -> list[tuple[str, list[str], str]]:
    specs: list[tuple[str, list[str], str]] = []
    for plan_name in plans:
        for method in methods:
            for state_format in state_formats:
                label = f"run all provision {method} ({plan_name}, {state_format})"
                args: list[str] = []
                if method == "local":
                    args.append("--feeling-safe")
                args.extend(
                    [
                        "run",
                        "--scratch",
                        "-a",
                        "provision",
                        "--how",
                        method,
                        "plan",
                        "-n",
                        plan_name,
                    ]
                )
                specs.append((label, args, state_format))
    return specs


def main() -> int:
    repo = REPO.resolve()
    work_dir = WORK_DIR.resolve()
    profile_dir = (repo / SYNTHETIC_RUNS_PROFILE_DIR).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    require_synthetic_plan(work_dir)

    specs = iter_run_specs(PLANS, PROVISION_METHODS, STATE_FORMATS)

    print(f"Repository: {repo}", file=sys.stderr)
    print(f"Work directory: {work_dir}", file=sys.stderr)
    print(f"Python: {PYTHON}", file=sys.stderr)
    print(f"Profile directory: {profile_dir}", file=sys.stderr)
    print(
        f"Matrix: {len(PLANS)} plan(s) x {len(PROVISION_METHODS)} method(s) x "
        f"{len(STATE_FORMATS)} state format(s) = {len(specs)} profile run(s)",
        file=sys.stderr,
    )

    for label, args, state_format in specs:
        prof_path = profile_dir / f"{profile_safe_name(label)}.prof"
        env = build_subprocess_env(repo, state_format)
        print(f"Profiling {label}...", file=sys.stderr)
        completed = run_cprofile(PYTHON, work_dir, env, args, prof_path)
        if completed.returncode != 0:
            print(f"Warning: {label} exited {completed.returncode}", file=sys.stderr)
        print(f"  -> {prof_path} (TMT_STATE_FORMAT={state_format})", file=sys.stderr)

    print("\nDone. Run: python3 tests/performance/summarize_profiles.py", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
