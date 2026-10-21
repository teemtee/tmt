#!/usr/bin/env python3
# Dependencies must match the uv.lock
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
TESTS_DIR = ROOT_DIR / "tests"

subprocess.run(
    [
        "coverage",
        "run",
        "--source=tmt",
        "-m",
        "pytest",
        "-vvv",
        "-ra",
        "--showlocals",
        "-n",
        "0",
        str(TESTS_DIR),
    ],
    cwd=ROOT_DIR,
    check=True,
)
subprocess.run(
    ["coverage", "report"],
    cwd=ROOT_DIR,
    check=True,
)
subprocess.run(
    ["coverage", "annotate"],
    cwd=ROOT_DIR,
    check=True,
)
