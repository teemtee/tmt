#!/usr/bin/env python3
"""
Summarize cProfile ``.prof`` files from performance profiling scripts.
"""

from __future__ import annotations

import dataclasses
import pstats
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from profile_lib import COMMON_COMMANDS_PROFILE_DIR, profile_safe_name

# Standalone script: do not import tmt (see pyproject.toml TID251 for tests/performance/*).

ProfileFuncKey = tuple[str, int, str]
ProfileStatsEntry = tuple[int, int, float, float, dict[Any, int]]
ProfileStatsDict = dict[ProfileFuncKey, ProfileStatsEntry]


@dataclasses.dataclass(frozen=True)
class HotspotSpec:
    """One function to track in profile summary tables."""

    column: str
    func_name: str
    path_suffix: str
    exact_path_end: str | None = None


REPO = Path.cwd()
TOP_N = 25
MARKDOWN = False
TABLE_TITLE = "Cross-command comparison (cProfile)"

# ``None`` = every ``*.prof`` in PROFILE_DIR.
LABELS: list[str] | None = None
# otherwise explicit labels (must match the profiler's safe
# .prof basename via profile_safe_name()).
# LABELS: list[str] | None = [
#     "tests ls",
#     "plans ls",
#     "stories ls",
#     "tests show (1 test)",
#     "run discover (core)",
#     "lint",
# ]

# --- Common command preset ---------------------------------------------------
PROFILE_DIR = COMMON_COMMANDS_PROFILE_DIR
# Profile shown in the in-depth hotspot + top-functions section. ``None`` skips it.
DETAIL_LABEL: str | None = "tests ls"
# Hotspot columns for the comparison table.
HOTSPOT_SPECS: tuple[HotspotSpec, ...] = (
    HotspotSpec("_load_keys", "_load_keys", "tmt/utils/__init__.py"),
    HotspotSpec("logger.debug", "debug", "tmt/log.py", exact_path_end="tmt/log.py"),
    HotspotSpec("_format_dict", "_format_dict", "tmt/utils/__init__.py"),
)
# Extra hotspots for the detail section only (may overlap with HOTSPOT_SPECS).
DETAIL_HOTSPOT_SPECS: tuple[HotspotSpec, ...] = (
    HotspotSpec("indent", "indent", "tmt/log.py", exact_path_end="tmt/log.py"),
)

# --- Synthetic full-run preset (example) -----------------------------------
# from profile_lib import SYNTHETIC_RUNS_PROFILE_DIR
# PROFILE_DIR = SYNTHETIC_RUNS_PROFILE_DIR
# DETAIL_LABEL = "run all provision virtual (true, yaml)"
# TABLE_TITLE = "Synthetic full-run comparison (cProfile)"
# HOTSPOT_SPECS = (
#     HotspotSpec("execute", "execute", "steps/execute/internal.py"),
#     HotspotSpec("_run_guest_command", "_run_guest_command", "tmt/guest/__init__.py"),
#     HotspotSpec("_save_results", "_save_results", "tmt/steps/__init__.py"),
#     HotspotSpec("to_yaml", "to_yaml", "tmt/utils/__init__.py"),
#     HotspotSpec("write_state", "write_state", "tmt/base/run.py"),
# )
# DETAIL_HOTSPOT_SPECS = (
#     HotspotSpec("push", "push", "tmt/guest/__init__.py"),
#     HotspotSpec("pull", "pull", "tmt/guest/__init__.py"),
#     HotspotSpec("create_wrappers", "create_wrappers", "tmt/steps/context/pidfile.py"),
#     HotspotSpec("save (guest)", "save", "tmt/guest/__init__.py"),
# )


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
    profile_path: Path
    hotspots: dict[str, FunctionStats]


def load_profile_stats(prof_path: Path) -> tuple[float, ProfileStatsDict]:
    profile = cast(Any, pstats.Stats(str(prof_path)))
    total_tt = float(profile.total_tt)
    raw_stats = cast(ProfileStatsDict, profile.stats)
    return total_tt, raw_stats


def find_stat(stats: ProfileStatsDict, spec: HotspotSpec) -> FunctionStats:
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


def extract_metrics(
    prof_path: Path,
    label: str,
    hotspot_specs: Sequence[HotspotSpec],
) -> ProfileMetrics:
    total_tt, raw_stats = load_profile_stats(prof_path)
    hotspots = {spec.column: find_stat(raw_stats, spec) for spec in hotspot_specs}
    return ProfileMetrics(
        label=label,
        total_tt=total_tt,
        profile_path=prof_path,
        hotspots=hotspots,
    )


def iter_profile_files(profile_dir: Path) -> list[tuple[str, Path]]:
    if LABELS is not None:
        items: list[tuple[str, Path]] = []
        for label in LABELS:
            prof_path = profile_dir / f"{profile_safe_name(label)}.prof"
            if prof_path.is_file():
                items.append((label, prof_path))
            else:
                print(f"Warning: missing profile for {label}: {prof_path}", file=sys.stderr)
        return items

    return [(path.stem, path) for path in sorted(profile_dir.glob("*.prof"))]


def format_function_cell(stats: FunctionStats, total_tt: float) -> str:
    if stats.ncalls == 0 and stats.cumtime == 0:
        return "—"
    pct = stats.pct(total_tt)
    return f"{stats.cumtime:.2f}s ({pct:.1f}%)"


def print_cross_command_table(
    metrics: Sequence[ProfileMetrics],
    hotspot_specs: Sequence[HotspotSpec],
    markdown: bool,
    title: str,
) -> None:
    headers = [
        "Command",
        "Profile total_tt (s)",
        *[spec.column for spec in hotspot_specs],
    ]
    rows: list[list[str]] = [
        [
            metric.label,
            f"{metric.total_tt:.2f}",
            *[
                format_function_cell(metric.hotspots[spec.column], metric.total_tt)
                for spec in hotspot_specs
            ],
        ]
        for metric in metrics
    ]

    if markdown:
        print(f"## {title}\n")
        print("| " + " | ".join(headers) + " |")
        print("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            print("| " + " | ".join(row) + " |")
        print()
        print("Hotspot percentages are cumulative time as % of profile `total_tt`.")
    else:
        col_widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
        print(title)
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
    table_specs: Sequence[HotspotSpec],
    detail_specs: Sequence[HotspotSpec],
) -> None:
    total_tt, raw_stats = load_profile_stats(prof_path)
    tracked_specs = (*table_specs, *detail_specs)
    hotspots = {spec.column: find_stat(raw_stats, spec) for spec in tracked_specs}

    if markdown:
        print(f"## In-depth profile: `{title}`\n")
        print(f"Profile file: `{prof_path}`")
        print(f"Profile `total_tt`: {total_tt:.2f}s")
        print()
        print("| Hotspot | Calls | Total time | Cumulative | % of total |")
        print("| --- | --- | --- | --- | --- |")
    else:
        print(f"{title} — profile total_tt: {total_tt:.2f}s")
        print(f"Profile file: {prof_path}")
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


def main() -> int:
    profile_dir = (REPO / PROFILE_DIR).resolve()
    if not profile_dir.is_dir():
        raise SystemExit(f"Profile directory not found: {profile_dir}")

    profile_files = iter_profile_files(profile_dir)
    if not profile_files:
        raise SystemExit(f"No .prof files found in {profile_dir}")

    detail_specs = tuple(
        spec
        for spec in DETAIL_HOTSPOT_SPECS
        if spec.column not in {hotspot.column for hotspot in HOTSPOT_SPECS}
    )
    metrics = [
        extract_metrics(prof_path, label, HOTSPOT_SPECS) for label, prof_path in profile_files
    ]

    print_cross_command_table(metrics, HOTSPOT_SPECS, MARKDOWN, TABLE_TITLE)

    if DETAIL_LABEL is not None:
        detail_prof = profile_dir / f"{profile_safe_name(DETAIL_LABEL)}.prof"
        if detail_prof.is_file():
            print()
            print_profile_detail(
                detail_prof,
                DETAIL_LABEL,
                TOP_N,
                MARKDOWN,
                HOTSPOT_SPECS,
                detail_specs,
            )
        else:
            print(
                f"Warning: {detail_prof.name} not found; skipping detail section.",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
