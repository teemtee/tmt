#!/usr/bin/env python3
"""
Create synthetic tmt plans and tests for performance experiments.

Edit the settings in ``profile_lib.py``, then from the tmt git tree::

    python3 tests/performance/create_synthetic_plan.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import jinja2
from profile_lib import PERF_DIR, SYNTHETIC_COUNT, SYNTHETIC_DIR

REPO = Path.cwd()

TEMPLATE_DIR = PERF_DIR / "templates"
TESTS_TEMPLATE = TEMPLATE_DIR / "tests.fmf.j2"
PLAN_TEMPLATE = TEMPLATE_DIR / "plan.fmf.j2"
WRITE_SCRIPT_SOURCE = TEMPLATE_DIR / "write.sh"


def render_template(repo: Path, template: Path, **context: object) -> str:
    template_path = repo / template
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_path.parent),
        keep_trailing_newline=True,
        autoescape=False,  # noqa: S701
    )
    return environment.get_template(template_path.name).render(**context)


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> int:
    if SYNTHETIC_COUNT < 1:
        raise SystemExit("SYNTHETIC_COUNT must be at least 1")

    repo = REPO.resolve()
    tests_root = (repo / SYNTHETIC_DIR).resolve()
    sources = (
        TESTS_TEMPLATE,
        PLAN_TEMPLATE,
        WRITE_SCRIPT_SOURCE,
    )
    for source in sources:
        if not (repo / source).is_file():
            raise SystemExit(f"Missing source file: {repo / source}")

    tests_root.mkdir(parents=True, exist_ok=True)
    (tests_root / ".fmf").mkdir(parents=True, exist_ok=True)
    (tests_root / ".fmf" / "version").write_text("1")

    (tests_root / "tests.fmf").write_text(
        render_template(repo, TESTS_TEMPLATE, count=SYNTHETIC_COUNT),
    )
    (tests_root / "plan.fmf").write_text(render_template(repo, PLAN_TEMPLATE))
    copy_file(repo / WRITE_SCRIPT_SOURCE, tests_root / "write.sh")
    (tests_root / "write.sh").chmod(0o755)

    print(f"Repository: {repo}")
    print(f"Tests: {SYNTHETIC_COUNT} synthetic tests, plans true + write")
    print(f"Tests directory: {tests_root}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
