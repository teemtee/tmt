#!/usr/bin/env python3
"""
Profile common tmt CLI commands for performance investigation.

Reproduces wall-clock timings, cProfile cross-command comparison tables, and an
in-depth breakdown for ``tmt tests ls``. Intended to be run from the tmt git
tree using the in-tree package:

    cd /path/to/tmt
    python3 tests/performance/profile_common_commands.py

Profile output files are written to a temporary directory (or ``--profile-dir``).
Subprocesses set ``PYTHONPATH=<repo>`` so the in-tree package is used regardless of cwd.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import pstats
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

# Standalone script: do not import tmt (see pyproject.toml TID251 for tests/performance/*).

ProfileFuncKey = tuple[str, int, str]
ProfileStatsEntry = tuple[int, int, float, float, dict[Any, int]]
ProfileStatsDict = dict[ProfileFuncKey, ProfileStatsEntry]


@dataclasses.dataclass(frozen=True)
class CommandSpec:
    """One CLI invocation to profile."""

    label: str
    args: list[str]


DEFAULT_COMMANDS: list[CommandSpec] = [
    CommandSpec("tests ls", ["tests", "ls"]),
    CommandSpec("plans ls", ["plans", "ls"]),
    CommandSpec("stories ls", ["stories", "ls"]),
    CommandSpec(
        "tests show (1 test)",
        ["tests", "show", "/tests/provision/virtual/dependencies"],
    ),
    CommandSpec(
        "run discover (core)",
        [
            "run",
            "discover",
            "plan",
            "-n",
            "^/plans/features/core$",
        ],
    ),
    CommandSpec("lint", ["lint"]),
]


@dataclasses.dataclass
class FunctionStats:
    ncalls: int = 0
    tottime: float = 0.0
    cumtime: float = 0.0

    def pct(self, total_tt: float) -> float:
        if total_tt <= 0:
            return 0.0
        return 100.0 * self.cumtime / total_tt


@dataclasses.dataclass
class ProfileMetrics:
    label: str
    total_tt: float
    wall_avg: float
    load_keys: FunctionStats
    logger_debug: FunctionStats
    format_dict: FunctionStats
    indent: FunctionStats
    profile_path: Path


def load_profile_stats(prof_path: Path) -> tuple[float, ProfileStatsDict]:
    profile = cast(Any, pstats.Stats(str(prof_path)))
    total_tt = float(profile.total_tt)
    raw_stats = cast(ProfileStatsDict, profile.stats)
    return total_tt, raw_stats


def _find_stat(
    stats: ProfileStatsDict,
    func_name: str,
    path_suffix: str,
    exact_path_end: str | None = None,
) -> FunctionStats:
    for func, (_cc, nc, tt, ct, _callers) in stats.items():
        filename, _line, name = func
        if name != func_name or path_suffix not in filename:
            continue
        if exact_path_end is not None and not filename.endswith(exact_path_end):
            continue
        return FunctionStats(ncalls=nc, tottime=tt, cumtime=ct)
    return FunctionStats()


def extract_metrics(prof_path: Path, label: str) -> ProfileMetrics:
    total_tt, raw_stats = load_profile_stats(prof_path)

    return ProfileMetrics(
        label=label,
        total_tt=total_tt,
        wall_avg=0.0,
        load_keys=_find_stat(raw_stats, "_load_keys", "tmt/utils/__init__.py"),
        logger_debug=_find_stat(raw_stats, "debug", "tmt/log.py", exact_path_end="tmt/log.py"),
        format_dict=_find_stat(raw_stats, "_format_dict", "tmt/utils/__init__.py"),
        indent=_find_stat(raw_stats, "indent", "tmt/log.py", exact_path_end="tmt/log.py"),
        profile_path=prof_path,
    )


def build_subprocess_env(repo: Path) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(repo)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def run_wall_clock(
    python: str,
    repo: Path,
    args: list[str],
    runs: int,
) -> float:
    times: list[float] = []
    env = build_subprocess_env(repo)
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.run(
            [python, "-m", "tmt", *args],
            cwd=repo,
            env=env,
            capture_output=True,
            check=False,
        )
        times.append(time.perf_counter() - start)
    return statistics.mean(times)


def profile_safe_name(label: str) -> str:
    return label.replace(" ", "_").replace("(", "").replace(")", "")


def run_cprofile(
    python: str,
    repo: Path,
    args: list[str],
    prof_path: Path,
) -> None:
    prof_path.parent.mkdir(parents=True, exist_ok=True)
    env = build_subprocess_env(repo)
    subprocess.run(
        [
            python,
            "-m",
            "cProfile",
            "-o",
            str(prof_path),
            "-m",
            "tmt",
            *args,
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        check=False,
    )
    if not prof_path.is_file():
        raise RuntimeError(f"cProfile did not create {prof_path}")


def profile_commands(
    python: str,
    repo: Path,
    commands: Sequence[CommandSpec],
    profile_dir: Path,
    wall_runs: int,
) -> list[ProfileMetrics]:
    results: list[ProfileMetrics] = []
    for spec in commands:
        prof_path = profile_dir / f"{profile_safe_name(spec.label)}.prof"
        print(f"Profiling {spec.label}...", file=sys.stderr)
        run_cprofile(python, repo, spec.args, prof_path)
        metrics = extract_metrics(prof_path, spec.label)
        metrics.wall_avg = run_wall_clock(python, repo, spec.args, wall_runs)
        results.append(metrics)
    return results


def format_function_cell(stats: FunctionStats, total_tt: float) -> str:
    if stats.ncalls == 0 and stats.cumtime == 0:
        return "—"
    pct = stats.pct(total_tt)
    return f"{stats.cumtime:.2f}s ({pct:.1f}%)"


def print_cross_command_table(
    metrics: Sequence[ProfileMetrics],
    markdown: bool,
) -> None:
    headers = [
        "Command",
        "Profile total_tt (s)",
        "Wall avg (s)",
        "_load_keys",
        "logger.debug",
        "_format_dict",
    ]
    rows: list[list[str]] = [
        [
            m.label,
            f"{m.total_tt:.2f}",
            f"{m.wall_avg:.2f}",
            format_function_cell(m.load_keys, m.total_tt),
            format_function_cell(m.logger_debug, m.total_tt),
            format_function_cell(m.format_dict, m.total_tt),
        ]
        for m in metrics
    ]

    if markdown:
        print("## Cross-command comparison (cProfile)\n")
        print("| " + " | ".join(headers) + " |")
        print("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            print("| " + " | ".join(row) + " |")
        print()
        print(
            "Percentages in `_load_keys` / `logger.debug` / `_format_dict` "
            "are % of profile `total_tt`."
        )
        print("Invocation: `PYTHONPATH=<repo> python -m cProfile -m tmt …` with cwd=<repo>.")
    else:
        col_widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
        line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        print(line)
        print("-" * len(line))
        for row in rows:
            print("  ".join(row[i].ljust(col_widths[i]) for i in range(len(headers))))


def print_profile_detail(
    prof_path: Path,
    title: str,
    top_n: int,
    markdown: bool,
    metrics: ProfileMetrics | None = None,
) -> None:
    total_tt, raw_stats = load_profile_stats(prof_path)
    load_keys = _find_stat(raw_stats, "_load_keys", "tmt/utils/__init__.py")
    logger_debug = _find_stat(raw_stats, "debug", "tmt/log.py", exact_path_end="tmt/log.py")
    format_dict = _find_stat(raw_stats, "_format_dict", "tmt/utils/__init__.py")
    indent = _find_stat(raw_stats, "indent", "tmt/log.py", exact_path_end="tmt/log.py")

    if markdown:
        print(f"## In-depth profile: `{title}`\n")
        print(f"Profile file: `{prof_path}`")
        print(f"Profile `total_tt`: {total_tt:.2f}s")
        if metrics is not None:
            print(f"Wall avg: {metrics.wall_avg:.2f}s")
        print()
        print("| Hotspot | Calls | Total time | Cumulative | % of total |")
        print("| --- | --- | --- | --- | --- |")
        for name, hotspot in (
            ("`_load_keys`", load_keys),
            ("`logger.debug`", logger_debug),
            ("`_format_dict`", format_dict),
            ("`indent`", indent),
        ):
            if hotspot.ncalls:
                pct = hotspot.pct(total_tt)
                print(
                    f"| {name} | {hotspot.ncalls} | "
                    f"{hotspot.tottime:.3f}s | {hotspot.cumtime:.3f}s | {pct:.1f}% |"
                )
        print()
        print("| Function | Calls | Total time | Cumulative | % of total |")
        print("| --- | --- | --- | --- | --- |")
    else:
        print(f"{title} — profile total_tt: {total_tt:.2f}s")
        print(f"Profile file: {prof_path}")
        if metrics is not None:
            print(f"Wall avg: {metrics.wall_avg:.2f}s")
        print()
        print(f"{'Hotspot':<16} {'ncalls':>10} {'tottime':>10} {'cumtime':>10} {'%':>8}")
        for name, hotspot in (
            ("_load_keys", load_keys),
            ("logger.debug", logger_debug),
            ("_format_dict", format_dict),
            ("indent", indent),
        ):
            if hotspot.ncalls:
                pct = hotspot.pct(total_tt)
                print(
                    f"{name:<16} {hotspot.ncalls:>10} "
                    f"{hotspot.tottime:>10.3f} {hotspot.cumtime:>10.3f} {pct:>7.1f}%"
                )
        print()
        print(f"{'Function':<40} {'ncalls':>10} {'tottime':>10} {'cumtime':>10} {'%':>8}")

    def entry_cumtime(item: tuple[ProfileFuncKey, ProfileStatsEntry]) -> float:
        return -item[1][3]

    for func, (_cc, nc, tt, ct, _callers) in sorted(
        raw_stats.items(),
        key=entry_cumtime,
    )[:top_n]:
        filename, line_no, name = func
        short_file = Path(filename).name
        label = f"{name}:{line_no} ({short_file})"
        pct = 100.0 * ct / total_tt if total_tt else 0.0
        if markdown:
            print(f"| `{name}` | {nc} | {tt:.3f}s | {ct:.3f}s | {pct:.1f}% |")
        else:
            print(f"{label:<40} {nc:>10} {tt:>10.3f} {ct:>10.3f} {pct:>7.1f}%")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile common tmt commands (wall clock + cProfile tables).",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="tmt git repository root (default: current directory)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to run python -m tmt",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="Directory for .prof files (default: <repo>/.profile_common_commands)",
    )
    parser.add_argument(
        "--wall-runs",
        type=int,
        default=3,
        metavar="N",
        help="Wall-clock repetitions per command without cProfile (default: 3)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        metavar="N",
        help="Top N functions per in-depth profile section (default: 25)",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Emit markdown tables instead of plain text",
    )
    parser.add_argument(
        "--cross-command-only",
        action="store_true",
        help="Skip in-depth profile sections",
    )
    parser.add_argument(
        "--tests-ls-only",
        action="store_true",
        help="Profile only tmt tests ls (cross-command table + detail)",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    repo = args.repo.resolve()
    profile_dir = args.profile_dir or (repo / ".profile_common_commands")
    profile_dir.mkdir(parents=True, exist_ok=True)

    commands = (
        [CommandSpec("tests ls", ["tests", "ls"])]
        if args.tests_ls_only
        else list(DEFAULT_COMMANDS)
    )

    print(f"Repository: {repo}", file=sys.stderr)
    print(f"Python: {args.python}", file=sys.stderr)
    print(f"PYTHONPATH: {build_subprocess_env(repo)['PYTHONPATH']}", file=sys.stderr)
    print(f"Profile directory: {profile_dir}", file=sys.stderr)

    metrics = profile_commands(
        args.python,
        repo,
        commands,
        profile_dir,
        args.wall_runs,
    )

    metrics_by_label = {metric.label: metric for metric in metrics}

    print_cross_command_table(metrics, args.markdown)

    if not args.cross_command_only:
        tests_ls_prof = profile_dir / "tests_ls.prof"
        if tests_ls_prof.is_file():
            print()
            print_profile_detail(
                tests_ls_prof,
                "tests ls",
                args.top,
                args.markdown,
                metrics_by_label.get("tests ls"),
            )
        else:
            print("Warning: tests_ls.prof not found; skipping detail section.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
