#!/usr/bin/env python3
"""
Create synthetic tmt plans and tests for performance experiments.

Renders templates from ``tests/performance/templates/`` into a nested fmf tree
under ``tests/performance/synthetic/``. Templates use a ``.fmf.j2`` suffix so
they are not loaded as fmf metadata under ``tests/``.

The generated ``plan.fmf`` defines two plans, ``true`` and ``write``; the write
plan sets ``context.type: write`` so tests run ``write.sh`` via fmf adjust.

Example::

    cd /path/to/tmt
    python3 tests/performance/create_synthetic_plan.py
    cd tests/performance/synthetic
    tmt run discover plan -n true
    tmt run discover plan -n write
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import jinja2

PERF_DIR = Path("tests/performance")
TEMPLATE_DIR = PERF_DIR / "templates"
DEFAULT_SYNTHETIC_DIR = PERF_DIR / "synthetic"
DEFAULT_COUNT = 200
FMF_VERSION = "1"

TESTS_TEMPLATE = TEMPLATE_DIR / "tests.fmf.j2"
PLAN_TEMPLATE = TEMPLATE_DIR / "plan.fmf.j2"
WRITE_SCRIPT_SOURCE = TEMPLATE_DIR / "write.sh"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic tmt tests and plans.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="tmt repository root (default: current directory)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        metavar="N",
        help=f"Number of synthetic tests (default: {DEFAULT_COUNT})",
    )
    parser.add_argument(
        "--tests-dir",
        type=Path,
        default=DEFAULT_SYNTHETIC_DIR,
        help=f"Output tree relative to --repo (default: {DEFAULT_SYNTHETIC_DIR})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing generated tree before creating new files",
    )
    return parser.parse_args(argv)


def render_template(repo: Path, template: Path, **context: object) -> str:
    template_path = repo / template
    environment = jinja2.Environment(
        autoescape=True,
        loader=jinja2.FileSystemLoader(template_path.parent),
        keep_trailing_newline=True,
    )
    return environment.get_template(template_path.name).render(**context)


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.count < 1:
        raise SystemExit("--count must be at least 1")

    repo = args.repo.resolve()
    tests_root = (repo / args.tests_dir).resolve()
    sources = (
        TESTS_TEMPLATE,
        PLAN_TEMPLATE,
        WRITE_SCRIPT_SOURCE,
    )
    for source in sources:
        if not (repo / source).is_file():
            raise SystemExit(f"Missing source file: {repo / source}")

    if args.clean and tests_root.exists():
        shutil.rmtree(tests_root)

    tests_root.mkdir(parents=True, exist_ok=True)
    (tests_root / ".fmf").mkdir(parents=True, exist_ok=True)
    (tests_root / ".fmf" / "version").write_text(FMF_VERSION)

    (tests_root / "tests.fmf").write_text(render_template(repo, TESTS_TEMPLATE, count=args.count))
    (tests_root / "plan.fmf").write_text(render_template(repo, PLAN_TEMPLATE))
    copy_file(repo / WRITE_SCRIPT_SOURCE, tests_root / "write.sh")
    (tests_root / "write.sh").chmod(0o755)

    rel_root = tests_root.relative_to(repo)
    print(f"Repository: {repo}")
    print(f"Tests: {args.count} synthetic tests, plans true + write")
    print(f"Tests directory: {tests_root}")
    print()
    print("Created synthetic plans and tests.")
    print(f"  cd {rel_root}")
    print("  tmt run discover plan -n true")
    print("  tmt run discover plan -n write")
    print()
    print("Consider gitignoring:", rel_root)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
