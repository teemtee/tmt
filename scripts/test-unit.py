#!/usr/bin/env python3
# Dependencies must match the uv.lock
import subprocess
from pathlib import Path

from _pytest.config import _console_main as pytest_run

ROOT_DIR = Path(__file__).parent.parent
TESTS_DIR = ROOT_DIR / "tests"
TESTS_UNIT_DIR = TESTS_DIR / "unit"

subprocess.run(["make", "images/test"], cwd=ROOT_DIR, check=True)

raise SystemExit(
    pytest_run(
        [
            "-vvv",
            "-ra",
            "--showlocals",
            "-n",
            "0",
            str(TESTS_UNIT_DIR),
        ]
    )
)
