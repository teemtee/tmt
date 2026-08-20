#!/usr/bin/env python3
"""
Create two tmt plans and ~N synthetic shell tests per plan for performance experiments.

One plan discovers only ``/usr/bin/true`` noop tests; the other discovers only
``write.sh`` tests that write random data to temporary files. Output lives under
``tests/performance/synthetic/`` by default as a nested fmf tree.

Example::

    cd /path/to/tmt
    python3 tests/performance/create_synthetic_plan.py --count 200
    cd tests/performance/synthetic
    tmt -n plan-true run discover
    tmt -n plan-write run discover
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

TRUE_TEST_FMF = """\
summary: Synthetic noop test {index:04d}
test: /usr/bin/true
framework: shell
tag: synthetic-true
tier: 3
duration: 1m
"""

WRITE_TEST_FMF = """\
summary: Synthetic random write test {index:04d}
test: ./write.sh
framework: shell
tag: synthetic-write
tier: 3
duration: 1m
"""

WRITE_SCRIPT = """\
#!/bin/bash
set -eu
workdir="${TMT_TEST_DATA:-${TMPDIR:-/tmp}/tmt-synthetic-write}"
mkdir -p "${workdir}/synthetic-write"
for index in 1 2 3 4 5; do
    head -c 4096 /dev/urandom | base64 > "${workdir}/synthetic-write/blob-${index}.dat"
done
"""

FMF_VERSION = "1"

TRUE_PLAN_FMF = """\
summary: Synthetic noop performance plan ({count} /usr/bin/true tests)
description:
    Generated noop shell tests for metadata and run performance experiments.
discover:
    how: fmf
    filter: tag:synthetic-true
provision:
    how: local
execute:
    how: tmt
"""

WRITE_PLAN_FMF = """\
summary: Synthetic write performance plan ({count} write.sh tests)
description:
    Generated shell tests that write random data to files for run performance
    experiments.
discover:
    how: fmf
    filter: tag:synthetic-write
provision:
    how: local
execute:
    how: tmt
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic tmt tests and two discoverable plans.",
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
        default=200,
        metavar="N",
        help="Number of tests per plan (default: 200 noop + 200 write)",
    )
    parser.add_argument(
        "--tests-dir",
        type=Path,
        default=Path("tests/performance/synthetic"),
        help="Tests tree relative to --repo (default: tests/performance/synthetic)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing generated tests and plans before creating new ones",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing files",
    )
    return parser.parse_args(argv)


def write_file(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"would write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def remove_tree(path: Path, dry_run: bool) -> None:
    if not path.exists():
        return
    if dry_run:
        print(f"would remove {path}")
        return
    if path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def create_true_test(test_dir: Path, index: int, dry_run: bool) -> None:
    write_file(
        test_dir / "main.fmf",
        TRUE_TEST_FMF.format(index=index),
        dry_run,
    )


def create_write_test(test_dir: Path, index: int, dry_run: bool) -> None:
    write_file(test_dir / "main.fmf", WRITE_TEST_FMF.format(index=index), dry_run)
    write_file(test_dir / "write.sh", WRITE_SCRIPT, dry_run)
    if not dry_run:
        (test_dir / "write.sh").chmod(0o755)


def create_fmf_root(tree_root: Path, dry_run: bool) -> None:
    write_file(tree_root / ".fmf" / "version", FMF_VERSION, dry_run)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.count < 1:
        raise SystemExit("--count must be at least 1")

    repo = args.repo.resolve()
    tests_root = (repo / args.tests_dir).resolve()
    true_plan_path = tests_root / "plan-true.fmf"
    write_plan_path = tests_root / "plan-write.fmf"

    if args.clean:
        remove_tree(tests_root, args.dry_run)

    print(f"Repository: {repo}")
    print(f"Tests: {args.count} noop + {args.count} write = {args.count * 2} total")
    print(f"Tests directory: {tests_root}")
    print(f"Noop plan: {true_plan_path}")
    print(f"Write plan: {write_plan_path}")

    for index in range(1, args.count + 1):
        create_true_test(tests_root / "true" / f"{index:04d}", index, args.dry_run)

    for index in range(1, args.count + 1):
        create_write_test(tests_root / "write" / f"{index:04d}", index, args.dry_run)

    create_fmf_root(tests_root, args.dry_run)
    write_file(
        true_plan_path,
        TRUE_PLAN_FMF.format(count=args.count),
        args.dry_run,
    )
    write_file(
        write_plan_path,
        WRITE_PLAN_FMF.format(count=args.count),
        args.dry_run,
    )

    if not args.dry_run:
        try:
            rel_root = tests_root.relative_to(repo)
        except ValueError:
            rel_root = tests_root

        print()
        print("Created synthetic plans and tests.")
        print(f"  cd {rel_root}")
        print("  tmt -n plan-true tests ls")
        print("  tmt -n plan-write tests ls")
        print("  tmt -n plan-true run discover")
        print("  tmt -n plan-write run discover")
        print()
        print("Consider gitignoring:", rel_root)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
