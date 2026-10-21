#!/usr/bin/env python3
# Dependencies must match the uv.lock
import subprocess
from pathlib import Path

from _pytest.config import _console_main as pytest_run

ROOT_DIR = Path(__file__).parent.parent
TESTS_DIR = ROOT_DIR / "tests"
TESTS_INTEGRATION_DIR = TESTS_DIR / "integration"

ret = pytest_run(
    [
        "-vvv",
        "-ra",
        "--showlocals",
        "-n",
        "0",
        str(TESTS_INTEGRATION_DIR),
    ]
)
if ret:
    raise SystemExit(ret)

subprocess.run(
    [
        "requre-patch",
        "purge",
        "--replaces",
        ":milestone_url:str:SomeText",
        "--replaces",
        ":latency:float:0",
        f"{TESTS_INTEGRATION_DIR}/test_data/test_nitrate/*",
    ],
    cwd=ROOT_DIR,
    check=True,
)
