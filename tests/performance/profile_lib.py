"""Shared helpers and settings for standalone performance profiling scripts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PERF_DIR = Path("tests/performance")
SYNTHETIC_DIR = PERF_DIR / "synthetic"
SYNTHETIC_COUNT = 200


def profile_safe_name(label: str) -> str:
    return label.replace(" ", "_").replace("(", "").replace(")", "")


def build_subprocess_env(repo: Path, state_format: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(repo)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if state_format is not None:
        env["TMT_STATE_FORMAT"] = state_format
    return env


def run_cprofile(
    python: str,
    cwd: Path,
    env: dict[str, str],
    tmt_args: list[str],
    prof_path: Path,
) -> subprocess.CompletedProcess[bytes]:
    prof_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [python, "-m", "cProfile", "-o", str(prof_path), "-m", "tmt", *tmt_args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
    )
    if not prof_path.is_file():
        raise RuntimeError(f"cProfile did not create {prof_path}")
    return completed
