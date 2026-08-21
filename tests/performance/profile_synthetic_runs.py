#!/usr/bin/env python3
"""
Profile full synthetic tmt runs for performance investigation.

Profiles ``tmt run -a provision --how {local|virtual|container}`` for both
synthetic plans (200 ``/usr/bin/true`` tests and 200 ``write.sh`` tests).
Creates the nested fmf tree via ``create_synthetic_plan.py`` when missing.

By default sweeps ``TMT_STATE_FORMAT`` (``yaml`` and ``json``).

Cross-command tables highlight run-phase hotspots (execute, guest I/O, state
serialization) rather than metadata loading.

Profiles reflect whatever ``ruamel.yaml`` / ``ruamel.yaml.clib`` setup is in the
active Python environment.

Example::

    cd /path/to/tmt
    python3 tests/performance/profile_synthetic_runs.py

    # Smaller matrix (noop plan, local only, yaml only)
    python3 tests/performance/profile_synthetic_runs.py \\
        --plans true --methods local --state-formats yaml

Profile output files are written to ``.profile_synthetic_runs/`` (or ``--profile-dir``).
Runs use ``PYTHONPATH=<repo>`` so in-tree ``tmt`` is used when cwd is the nested tree.

The expected runtime for this full script is several hours.
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

PERF_DIR = Path("tests/performance")
DEFAULT_SYNTHETIC_DIR = PERF_DIR / "synthetic"
DEFAULT_SYNTHETIC_PLANS = ("true", "write")
DEFAULT_SYNTHETIC_COUNT = 200
DEFAULT_PROVISION_METHODS = ("local", "virtual", "container")
DEFAULT_STATE_FORMATS = ("yaml", "json")


@dataclasses.dataclass(frozen=True)
class HotspotSpec:
    """One function to track in cross-command tables."""

    column: str
    func_name: str
    path_suffix: str
    exact_path_end: str | None = None


@dataclasses.dataclass(frozen=True)
class CommandSpec:
    """One CLI invocation to profile."""

    label: str
    args: list[str]
    cwd: Path
    variant: str
    method: str
    state_format: str


RUN_HOTSPOT_SPECS: tuple[HotspotSpec, ...] = (
    HotspotSpec("execute", "execute", "steps/execute/internal.py"),
    HotspotSpec("_run_guest_command", "_run_guest_command", "tmt/guest/__init__.py"),
    HotspotSpec("_save_results", "_save_results", "tmt/steps/__init__.py"),
    HotspotSpec("to_yaml", "to_yaml", "tmt/utils/__init__.py"),
    HotspotSpec("write_state", "write_state", "tmt/base/run.py"),
)

DETAIL_HOTSPOT_SPECS: tuple[HotspotSpec, ...] = (
    HotspotSpec("push", "push", "tmt/guest/__init__.py"),
    HotspotSpec("pull", "pull", "tmt/guest/__init__.py"),
    HotspotSpec("create_wrappers", "create_wrappers", "tmt/steps/context/pidfile.py"),
    HotspotSpec("save (guest)", "save", "tmt/guest/__init__.py"),
)


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
class RunProfileMetrics:
    label: str
    variant: str
    method: str
    state_format: str
    total_tt: float
    wall_avg: float
    profile_path: Path
    hotspots: dict[str, FunctionStats]
    exit_code: int = 0


def load_profile_stats(prof_path: Path) -> tuple[float, ProfileStatsDict]:
    profile = cast(Any, pstats.Stats(str(prof_path)))
    total_tt = float(profile.total_tt)
    raw_stats = cast(ProfileStatsDict, profile.stats)
    return total_tt, raw_stats


def _find_stat(
    stats: ProfileStatsDict,
    spec: HotspotSpec,
) -> FunctionStats:
    best = FunctionStats()
    for func, (_cc, nc, tt, ct, _callers) in stats.items():
        filename, _line, name = func
        normalized = filename.replace("\\", "/")
        if name != spec.func_name or spec.path_suffix not in normalized:
            continue
        if spec.exact_path_end is not None and not normalized.endswith(spec.exact_path_end):
            continue
        if ct > best.cumtime:
            best = FunctionStats(ncalls=nc, tottime=tt, cumtime=ct)
    return best


def extract_run_metrics(
    prof_path: Path,
    spec: CommandSpec,
    hotspot_specs: Sequence[HotspotSpec],
) -> RunProfileMetrics:
    total_tt, raw_stats = load_profile_stats(prof_path)
    hotspots = {hotspot.column: _find_stat(raw_stats, hotspot) for hotspot in hotspot_specs}
    return RunProfileMetrics(
        label=spec.label,
        variant=spec.variant,
        method=spec.method,
        state_format=spec.state_format,
        total_tt=total_tt,
        wall_avg=0.0,
        profile_path=prof_path,
        hotspots=hotspots,
    )


def plan_variant_name(plan_name: str) -> str:
    if plan_name.startswith("plan-"):
        return plan_name.removeprefix("plan-")
    return plan_name


def build_subprocess_env(repo: Path, state_format: str) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(repo)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env["TMT_STATE_FORMAT"] = state_format
    return env


def synthetic_tree_ready(tests_root: Path) -> bool:
    return (tests_root / "plan.fmf").is_file() and (tests_root / "tests.fmf").is_file()


def ensure_synthetic_plan(
    python: str,
    repo: Path,
    synthetic_dir: Path,
    plans: Sequence[str],
    count: int,
    dry_run: bool,
) -> None:
    tests_root = (repo / synthetic_dir).resolve()
    if synthetic_tree_ready(tests_root):
        return
    script = repo / PERF_DIR / "create_synthetic_plan.py"
    if not script.is_file():
        raise SystemExit(f"Synthetic tree missing and {script} not found.")
    print(
        f"Creating synthetic tree ({count} tests, plans: {', '.join(plans)})...",
        file=sys.stderr,
    )
    cmd = [
        python,
        str(script),
        "--count",
        str(count),
        "--repo",
        str(repo),
        "--tests-dir",
        str(synthetic_dir),
    ]
    if dry_run:
        print(f"would run: {' '.join(cmd)}", file=sys.stderr)
        return
    subprocess.run(cmd, cwd=repo, check=True)


def synthetic_run_commands(
    repo: Path,
    synthetic_dir: Path,
    plans: Sequence[str],
    methods: Sequence[str],
    state_formats: Sequence[str],
) -> list[CommandSpec]:
    run_cwd = (repo / synthetic_dir).resolve()
    commands: list[CommandSpec] = []
    for plan_name in plans:
        variant = plan_variant_name(plan_name)
        for method in methods:
            for state_format in state_formats:
                label = f"run all provision {method} ({variant}, {state_format})"
                args = [
                    "--feeling-safe",
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
                commands.append(
                    CommandSpec(
                        label=label,
                        args=args,
                        cwd=run_cwd,
                        variant=variant,
                        method=method,
                        state_format=state_format,
                    )
                )
    return commands


def format_output_tail(output: bytes, max_lines: int = 12) -> str:
    text = output.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def run_tmt_subprocess(
    python: str,
    repo: Path,
    spec: CommandSpec,
    extra_args: list[str],
) -> subprocess.CompletedProcess[bytes]:
    env = build_subprocess_env(repo, spec.state_format)
    return subprocess.run(
        [python, *extra_args, "-m", "tmt", *spec.args],
        cwd=spec.cwd,
        env=env,
        capture_output=True,
        check=False,
    )


def profile_has_run_hotspots(metrics: RunProfileMetrics) -> bool:
    return any(hotspot.cumtime > 0.0 for hotspot in metrics.hotspots.values())


def report_run_failure(spec: CommandSpec, completed: subprocess.CompletedProcess[bytes]) -> None:
    print(
        f"Warning: {spec.label} exited {completed.returncode} "
        f"(wall/profile hotspots will be empty if the run did not execute tests).",
        file=sys.stderr,
    )
    stderr_tail = format_output_tail(completed.stderr)
    if stderr_tail:
        print(f"stderr tail for {spec.label}:", file=sys.stderr)
        print(stderr_tail, file=sys.stderr)


def run_wall_clock(
    python: str,
    repo: Path,
    spec: CommandSpec,
    runs: int,
) -> tuple[float, int]:
    times: list[float] = []
    last_exit = 0
    for _ in range(runs):
        start = time.perf_counter()
        completed = run_tmt_subprocess(python, repo, spec, [])
        last_exit = completed.returncode
        times.append(time.perf_counter() - start)
    return statistics.mean(times), last_exit


def profile_safe_name(label: str) -> str:
    return label.replace(" ", "_").replace("(", "").replace(")", "")


def run_cprofile(
    python: str,
    repo: Path,
    spec: CommandSpec,
    prof_path: Path,
) -> subprocess.CompletedProcess[bytes]:
    prof_path.parent.mkdir(parents=True, exist_ok=True)
    completed = run_tmt_subprocess(
        python,
        repo,
        spec,
        ["-m", "cProfile", "-o", str(prof_path)],
    )
    if not prof_path.is_file():
        raise RuntimeError(f"cProfile did not create {prof_path}")
    return completed


def profile_commands(
    python: str,
    repo: Path,
    commands: Sequence[CommandSpec],
    profile_dir: Path,
    wall_runs: int,
    hotspot_specs: Sequence[HotspotSpec],
) -> list[RunProfileMetrics]:
    results: list[RunProfileMetrics] = []
    for spec in commands:
        prof_path = profile_dir / f"{profile_safe_name(spec.label)}.prof"
        print(f"Profiling {spec.label}...", file=sys.stderr)
        profile_completed = run_cprofile(python, repo, spec, prof_path)
        metrics = extract_run_metrics(prof_path, spec, hotspot_specs)
        metrics.wall_avg, wall_exit = run_wall_clock(python, repo, spec, wall_runs)
        metrics.exit_code = (
            profile_completed.returncode if profile_completed.returncode != 0 else wall_exit
        )
        if profile_completed.returncode != 0:
            report_run_failure(spec, profile_completed)
        elif not profile_has_run_hotspots(metrics):
            print(
                f"Warning: {spec.label} finished but no run hotspots were found in the "
                f"profile (total_tt={metrics.total_tt:.2f}s). "
                "The run may have exited before execute or used a different tmt install.",
                file=sys.stderr,
            )
        results.append(metrics)
    return results


def format_function_cell(stats: FunctionStats, total_tt: float) -> str:
    if stats.ncalls == 0 and stats.cumtime == 0:
        return "—"
    pct = stats.pct(total_tt)
    return f"{stats.cumtime:.2f}s ({pct:.1f}%)"


def print_cross_command_table(
    metrics: Sequence[RunProfileMetrics],
    hotspot_specs: Sequence[HotspotSpec],
    markdown: bool,
) -> None:
    headers = [
        "Variant",
        "Method",
        "TMT_STATE_FORMAT",
        "Profile total_tt (s)",
        "Wall avg (s)",
        *[spec.column for spec in hotspot_specs],
    ]
    rows: list[list[str]] = [
        [
            metric.variant,
            metric.method,
            metric.state_format,
            f"{metric.total_tt:.2f}",
            f"{metric.wall_avg:.2f}",
            *[
                format_function_cell(metric.hotspots[spec.column], metric.total_tt)
                for spec in hotspot_specs
            ],
        ]
        for metric in metrics
    ]

    if markdown:
        print("## Synthetic full-run comparison (cProfile)\n")
        print("| " + " | ".join(headers) + " |")
        print("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            print("| " + " | ".join(row) + " |")
        print()
        print(
            "Percentages are cumulative time as % of profile `total_tt` "
            "(not additive across columns)."
        )
        print(
            "Invocation: `PYTHONPATH=<repo> TMT_STATE_FORMAT=<format> "
            "python -m cProfile -m tmt --feeling-safe run --scratch -a provision "
            "--how <method> plan -n <plan>` from `tests/performance/synthetic/`."
        )
    else:
        col_widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
        line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        print(line)
        print("-" * len(line))
        for row in rows:
            print("  ".join(row[i].ljust(col_widths[i]) for i in range(len(headers))))


def find_detail_metrics(
    metrics: Sequence[RunProfileMetrics],
    variant: str,
    method: str,
    state_format: str,
) -> RunProfileMetrics | None:
    for metric in metrics:
        if (
            metric.variant == variant
            and metric.method == method
            and metric.state_format == state_format
        ):
            return metric
    return None


def print_profile_detail(
    prof_path: Path,
    title: str,
    top_n: int,
    markdown: bool,
    metrics: RunProfileMetrics | None,
    table_specs: Sequence[HotspotSpec],
    detail_specs: Sequence[HotspotSpec],
) -> None:
    total_tt, raw_stats = load_profile_stats(prof_path)
    tracked_specs = (*table_specs, *detail_specs)
    hotspots = {spec.column: _find_stat(raw_stats, spec) for spec in tracked_specs}

    if markdown:
        print(f"## In-depth profile: `{title}`\n")
        print(f"Profile file: `{prof_path}`")
        print(f"Profile `total_tt`: {total_tt:.2f}s")
        if metrics is not None:
            print(f"Wall avg: {metrics.wall_avg:.2f}s")
        print()
        print("| Hotspot | Calls | Total time | Cumulative | % of total |")
        print("| --- | --- | --- | --- | --- |")
    else:
        print(f"{title} — profile total_tt: {total_tt:.2f}s")
        print(f"Profile file: {prof_path}")
        if metrics is not None:
            print(f"Wall avg: {metrics.wall_avg:.2f}s")
        print()
        print(f"{'Hotspot':<24} {'ncalls':>10} {'tottime':>10} {'cumtime':>10} {'%':>8}")

    for spec in tracked_specs:
        hotspot = hotspots[spec.column]
        if not hotspot.ncalls:
            continue
        pct = hotspot.pct(total_tt)
        if markdown:
            print(
                f"| `{spec.column}` | {hotspot.ncalls} | "
                f"{hotspot.tottime:.3f}s | {hotspot.cumtime:.3f}s | {pct:.1f}% |"
            )
        else:
            print(
                f"{spec.column:<24} {hotspot.ncalls:>10} "
                f"{hotspot.tottime:>10.3f} {hotspot.cumtime:>10.3f} {pct:>7.1f}%"
            )

    if markdown:
        print()
        print("| Function | Calls | Total time | Cumulative | % of total |")
        print("| --- | --- | --- | --- | --- |")
    else:
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
        description="Profile synthetic tmt full runs (wall clock + cProfile tables).",
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
        help="Directory for .prof files (default: <repo>/.profile_synthetic_runs)",
    )
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=DEFAULT_SYNTHETIC_DIR,
        help="Synthetic fmf tree relative to --repo (default: tests/performance/synthetic)",
    )
    parser.add_argument(
        "--synthetic-count",
        type=int,
        default=DEFAULT_SYNTHETIC_COUNT,
        metavar="N",
        help="Tests per plan when creating synthetic data (default: 200)",
    )
    parser.add_argument(
        "--plans",
        nargs="+",
        default=list(DEFAULT_SYNTHETIC_PLANS),
        metavar="PLAN",
        help="Synthetic plan names from plan.fmf (default: true write)",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=DEFAULT_PROVISION_METHODS,
        default=list(DEFAULT_PROVISION_METHODS),
        metavar="METHOD",
        help="Provision methods to profile (default: local virtual container)",
    )
    parser.add_argument(
        "--state-formats",
        nargs="+",
        choices=DEFAULT_STATE_FORMATS,
        default=list(DEFAULT_STATE_FORMATS),
        metavar="FORMAT",
        help="TMT_STATE_FORMAT values to sweep (default: yaml json)",
    )
    parser.add_argument(
        "--wall-runs",
        type=int,
        default=1,
        metavar="N",
        help="Wall-clock repetitions per command without cProfile (default: 1)",
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
        "--detail-variant",
        default="true",
        help="Plan variant for in-depth profile (default: true)",
    )
    parser.add_argument(
        "--detail-method",
        choices=DEFAULT_PROVISION_METHODS,
        default="local",
        help="Provision method for in-depth profile section (default: local)",
    )
    parser.add_argument(
        "--detail-state-format",
        choices=DEFAULT_STATE_FORMATS,
        default="yaml",
        help="TMT_STATE_FORMAT for in-depth profile (default: yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without profiling",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo = args.repo.resolve()
    profile_dir = args.profile_dir or (repo / ".profile_synthetic_runs")
    profile_dir.mkdir(parents=True, exist_ok=True)

    ensure_synthetic_plan(
        args.python,
        repo,
        args.synthetic_dir,
        args.plans,
        args.synthetic_count,
        args.dry_run,
    )

    commands = synthetic_run_commands(
        repo,
        args.synthetic_dir,
        args.plans,
        args.methods,
        args.state_formats,
    )

    print(f"Repository: {repo}", file=sys.stderr)
    print(f"Python: {args.python}", file=sys.stderr)
    print(f"Synthetic cwd: {repo / args.synthetic_dir}", file=sys.stderr)
    print(f"Profile directory: {profile_dir}", file=sys.stderr)
    print(
        f"Matrix: {len(args.plans)} plan(s) x {len(args.methods)} method(s) x "
        f"{len(args.state_formats)} state format(s) = {len(commands)} profile run(s)",
        file=sys.stderr,
    )

    if args.dry_run:
        for spec in commands:
            prof_path = profile_dir / f"{profile_safe_name(spec.label)}.prof"
            print(
                f"would profile {spec.label} "
                f"(TMT_STATE_FORMAT={spec.state_format}) -> {prof_path}",
                file=sys.stderr,
            )
        return 0

    metrics = profile_commands(
        args.python,
        repo,
        commands,
        profile_dir,
        args.wall_runs,
        RUN_HOTSPOT_SPECS,
    )

    print_cross_command_table(metrics, RUN_HOTSPOT_SPECS, args.markdown)

    if not args.cross_command_only:
        detail_label = (
            f"run all provision {args.detail_method} "
            f"({args.detail_variant}, {args.detail_state_format})"
        )
        detail_prof = profile_dir / f"{profile_safe_name(detail_label)}.prof"
        detail_metrics = find_detail_metrics(
            metrics,
            args.detail_variant,
            args.detail_method,
            args.detail_state_format,
        )
        if detail_prof.is_file():
            print()
            print_profile_detail(
                detail_prof,
                detail_label,
                args.top,
                args.markdown,
                detail_metrics,
                RUN_HOTSPOT_SPECS,
                DETAIL_HOTSPOT_SPECS,
            )
        else:
            print(
                f"Warning: {detail_prof.name} not found; skipping detail section.",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
