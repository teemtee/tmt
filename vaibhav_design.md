# Design: Ensure Artifact Packages Are Always Installed at Exact Version

## Context

Issue: #4838 — artifact plugin does not install/update/downgrade a required package
that is already on the system.

Scope answers (from team discussion):
- **All cases** from LecrisUT's test matrix must be handled from the start
- **Artifact** = discover-only provider (`repository-file:`, `repository-url:`) — adds a repo, no RPM download
- **Artifact (verify)** = download provider (`koji.build:`, `brew.build:`, `file:`, `copr.build:`) — downloads RPMs into `tmt-artifact-shared`
- **Download provider takes priority** when both types have the same package
- **Obsoletes** (`foo-ng` vs `foo`) — in scope
- **`--allow-downgrade` for transitive deps** — verified by POC

---

## POC Results (container, 2026-05-13/14)

### DNF5 (Fedora 42)

| Scenario | Command | Result |
|---|---|---|
| Not installed | `dnf5 install foo-1.1-1.nvra` | Installs from artifact repo ✓ |
| Installed at older version | `dnf5 install foo-1.1-1.nvra` | Upgrades (priority picks artifact) ✓ |
| Installed at NEWER version | `dnf5 install foo-1.1-1.nvra` | **Downgrades automatically** — no flag needed; repo priority drives it ✓ |
| Same NVRA, unknown origin | `dnf5 install foo-1.1-1.nvra` | No-op ("already installed") ✗ |
| Same NVRA, unknown origin fix | `dnf5 reinstall foo` | Reinstalls from artifact repo, fixes origin ✓ |
| Transitive dep downgrade (foo-devel-1.1 requires foo=1.1) | `dnf5 install --allow-downgrade foo-devel-1.1-nvra` | Downgrades `foo` as dep ✓ (needs `--allow-downgrade`) |
| Obsoletes (foo-ng installed, install foo-1.1) | `dnf5 install --allowerasing foo-1.1-nvra` | Removes foo-ng, installs foo-1.1 ✓ |
| `--repo=<id>` flag | EXISTS in DNF5 | Restricts install to one repo ✓ |
| `--from-repo=<id>` flag | EXISTS in DNF5 as alias for `--repo` | Also works ✓ |

**Key insight — DNF5 `--allow-downgrade` meaning:**
DNF5's help text says: *"Allow downgrade of **dependencies** for resolve of requested operation."*
The **directly named package** is always installed as specified (downgrade happens via priority).
`--allow-downgrade` is only needed to allow **transitive dependencies** to be downgraded.

**Key insight — DNF5 `%{from_repo}` reads from swdb, not from configured repos:**
DNF5 stores `from_repo` in its software database (swdb) at the time each package is installed
via DNF. `rpm -i` bypasses DNF entirely, leaving no swdb entry — so `%{from_repo}` returns
empty for packages installed that way (e.g. base image packages). `dnf reinstall` writes a
new swdb entry with the correct repo ID. This is why the reinstall step is required, and why
it correctly fixes origin: it is not a dynamic lookup against currently-configured repos.

### DNF4 (AlmaLinux 9)

| Scenario | Command | Result |
|---|---|---|
| Not installed | `dnf install foo-1.1-1.nvra` | Installs from artifact repo ✓ |
| Installed at older version | `dnf install foo-1.1-1.nvra` | Upgrades ✓ |
| Installed at NEWER version | `dnf install foo-1.1-1.nvra` | **Downgrades automatically** ✓ (same as DNF5) |
| Same NVRA, unknown origin | `dnf install foo-1.1-1.nvra` | No-op ("already installed") ✗ |
| Same NVRA, unknown origin fix | `dnf reinstall foo` | Reinstalls from artifact repo, fixes origin ✓ |
| Transitive dep downgrade (foo-devel-1.1 requires foo=1.1) | `dnf install foo-devel-1.1-nvra` | Downgrades `foo` as dep automatically — **no flag needed** ✓ |
| `--allow-downgrade` flag | **Does NOT exist** in DNF4 | — |
| `--repo=<id>` flag | EXISTS in DNF4 ✓ | — |

---

## The Two-Command Pattern

Applies to both DNF4 and DNF5. Run at order=50 in `_ensure_artifacts_installed`:

```
# Command 1: ensure correct version is installed
dnf install [--allow-downgrade] --allowerasing <nvra ...>
#   → handles: not installed, upgrade, direct downgrade, transitive dep downgrade,
#              obsoletes replacement (foo-ng ↔ foo)

# Command 2: fix swdb origin if same NVRA pre-installed without DNF (e.g. base image)
dnf reinstall <pkg-name ...>
#   → handles: same NVRA installed with empty/wrong swdb origin
```

`--allow-downgrade` is only added for **DNF5** (via `Options.allow_downgrade`).
DNF4 does not need it — transitive dep downgrade is automatic.

`--allowerasing` is added for **both DNF4 and DNF5** (via `Options.allow_erasing`).

Why this covers all version/origin states:

| State | Command 1 result | Command 2 result | Final origin |
|---|---|---|---|
| Not installed | Installs from artifact repo (priority wins) | No-op | artifact ✓ |
| Same NVRA, correct origin already | No-op | No-op | artifact ✓ |
| Same NVRA, empty swdb origin (base image pkg installed via rpm) | No-op ("already installed") | **Reinstalls, writes swdb entry** | artifact ✓ |
| Same NVRA, wrong swdb origin (installed from different repo) | No-op | Reinstalls from artifact (priority wins), updates swdb | artifact ✓ |
| Older version installed | Upgrades to artifact version | No-op | artifact ✓ |
| Newer version installed | **Downgrades** (repo priority drives it, no explicit flag needed) | No-op | artifact ✓ |
| foo-devel-1.1 required, foo-1.4 installed, foo-1.1 needed as dep | Downgrades foo as dep (DNF5: needs `--allow-downgrade`; DNF4: automatic) | No-op | artifact ✓ |
| foo-ng installed (Obsoletes foo < 1.4), install foo-1.1 | `--allowerasing` removes foo-ng, installs foo-1.1 | No-op | artifact ✓ |

---

## Failure Cases and How to Handle Them

### Failure 1: Obsoletes — `foo-ng` replaces `foo` or vice versa

**Scenario:**
```
System has foo-ng-1.4  (Provides: foo, Obsoletes: foo < 1.4)
Artifact has foo-1.1
User requests: foo
```
`dnf install foo-1.1-nvra` fails — DNF refuses because the installed `foo-ng-1.4`
obsoletes `foo-1.1`.

**Fix:** `--allowerasing` in Command 1 lets DNF remove `foo-ng-1.4` to satisfy
the install of `foo-1.1`. Risk: may remove packages depending on `foo-ng`.
This is acceptable — the user explicitly chose to test a specific artifact version
and must accept its replacement consequences.

Both DNF4 and DNF5 support `--allowerasing`.

### Failure 2: Multiple providers with same package at different versions

**Scenario:**
```
Artifact (discover-only):   foo-2.2  in repo
Artifact (download):        foo-2.4  downloaded to tmt-artifact-shared
```
Passing both `foo-2.2-nvra` and `foo-2.4-nvra` to a single `dnf install` command
causes a DNF conflict (two versions of the same package in one transaction).

**Fix:** priority ordering in `_ensure_artifacts_installed` — download providers
are processed first and "own" a package name; discover-only providers skip any
package name already claimed by a download provider. Two download providers having
the same package name is a hard error raised at validation time (extends
`_detect_duplicate_nvras`).

---

## Full Execution Flow

```
order=30  essential-requires install (createrepo_c)

order=50  prepare/artifact
          │
          ├── [existing] create shared repo dir
          ├── [existing] init providers + _detect_duplicate_nvras
          │     EXTENDED: also catch same pkg name from two download providers
          ├── [existing] fetch_contents + contribute_to_shared_repo (download providers)
          ├── [existing] createrepo on shared dir
          ├── [existing] install .repo files on guest
          ├── [existing] enumerate_artifacts(guest)
          ├── [existing] save_artifacts_metadata()
          │
          └── if self.data.verify:
              │
              ├── _compute_pkgs_to_verify(providers, guest)
              │     • collect pkg_names from tmt-managed install phases
              │     • resolve_provides(pkg_names, provider_repo_ids)  [one guest call]
              │     • intersect resolved names with artifact.version.name
              │     • returns dict[str, set[str]]  pkg_name → {repo_ids}
              │
              ├── _ensure_artifacts_installed(providers, pkgs_to_verify, guest)
              │     • collect NVRAs: download providers first, discover-only fills gaps
              │     • Command 1:
              │         DNF5: dnf5 install --allow-downgrade --allowerasing <nvra ...>
              │         DNF4: dnf  install --allowerasing <nvra ...>
              │       handles: install, upgrade, direct downgrade, transitive dep
              │                downgrade, obsoletes replacement
              │     • Command 2:
              │         dnf reinstall <pkg-name ...>
              │       handles: same-NVRA empty/wrong swdb origin fix
              │
              └── _inject_verify_phase(pkgs_to_verify)
                    schedules verify at order=79

order=70  requires install   (mostly no-ops; packages already at correct version)
order=75  recommends install (same)
order=79  verify-installation
          └── get_package_origin({foo, foo-devel, ...})
              → actual_origin in expected_repos → PASS
```

---

## Code Changes

### 1. `tmt/package_managers/__init__.py` — extend `Options`

Add two fields to the existing `Options` container:

```python
@container
class Options:
    # ... existing fields ...
    allow_downgrade: bool = False   # DNF5 only: allow transitive dep downgrades
    allow_erasing: bool = False     # both DNF4/5: allow removing obsoleting packages
```

### 2. `tmt/package_managers/dnf.py` — two changes

**a) Base `DnfEngine._extra_dnf_options`** — add `allow_erasing` (applies to both DNF4 and DNF5):

```python
def _extra_dnf_options(self, options: Options, command=None) -> Command:
    # ... existing excluded_packages and skip_missing handling ...
    if options.allow_erasing:
        extra_options += Command('--allowerasing')
    return extra_options
```

**b) New `Dnf5Engine._extra_dnf_options` override** — additionally handles `allow_downgrade`
(flag does not exist in DNF4, so it must only live in the DNF5 subclass):

```python
class Dnf5Engine(DnfEngine):
    # ... existing fields ...

    def _extra_dnf_options(self, options: Options, command=None) -> Command:
        extra_options = super()._extra_dnf_options(options, command)
        if options.allow_downgrade:
            extra_options += Command('--allow-downgrade')
        return extra_options
```

### 3. `tmt/steps/prepare/artifact/providers/__init__.py`

Add to `ArtifactProvider`:

```python
@property
def is_download_provider(self) -> bool:
    """True for koji/brew/file/copr.build providers; False for repository-file/url."""
    return False  # download provider subclasses override with return True
```

### 4. `tmt/steps/prepare/artifact/__init__.py`

**`go()` — updated section:**
```python
if self.data.verify:
    pkgs_to_verify = self._compute_pkgs_to_verify(providers, guest)
    if pkgs_to_verify:
        self._ensure_artifacts_installed(providers, pkgs_to_verify, guest)
        self._inject_verify_phase(pkgs_to_verify)
    else:
        self.verbose('No artifact packages in tmt install phases, skipping verification.')
```

**New `_compute_pkgs_to_verify`** — extracted from current `_inject_verify_phase`:
- Collects `pkg_names` from tmt-managed install phases (same logic as today)
- Calls `resolve_provides` once (not twice as currently)
- Intersects resolved names with artifact package names
- Returns `dict[str, set[str]]`  pkg_name → {repo_ids}

**New `_ensure_artifacts_installed`:**
```python
def _ensure_artifacts_installed(
    self,
    providers: list[ArtifactProvider],
    pkgs_to_verify: dict[str, set[str]],
    guest: Guest,
) -> None:
    from tmt.package_managers import Options, Package

    # Collect NEVRAs: download providers first, discover-only fills gaps.
    # If the same package name appears in both types, download provider wins.
    # By the time this runs, _detect_duplicate_nvras has already ensured no two
    # download providers share the same package name, so seen[] is a safeguard only.
    seen: dict[str, str] = {}   # pkg_name → provider raw_id
    nevras: list[Package] = []
    pkg_names: list[str] = []

    for download_first in (True, False):
        for provider in providers:
            if provider.is_download_provider != download_first:
                continue
            for artifact in provider.artifacts:
                name = artifact.version.name
                if name not in pkgs_to_verify or name in seen:
                    continue
                seen[name] = provider.raw_id
                nevras.append(Package(artifact.version.nevra))  # nevra includes epoch
                pkg_names.append(name)

    if not nevras:
        return

    install_options = Options(
        check_first=False,
        allow_downgrade=True,   # DNF5: allow transitive dep downgrades (ignored by DNF4)
        allow_erasing=True,     # both: allow removing obsoleting packages
    )
    reinstall_options = Options(check_first=False)

    guest.package_manager.install(*nevras, options=install_options)
    guest.package_manager.reinstall(*[Package(name) for name in pkg_names],
                                    options=reinstall_options)
```

Note: `reinstall()` already exists on the `PackageManager` base class and is implemented
in `DnfEngine` — no new method needed. This install+reinstall pattern mirrors
`Dnf.install_local()` (which uses the same two commands to work around BZ#1831022 —
DNF not recording repo origin for locally-installed packages).

**`_inject_verify_phase`** — simplified: takes `pkgs_to_verify` dict directly,
no longer calls `resolve_provides` or takes `guest` as argument.

**Extended `_detect_duplicate_nvras`** — also detect same package name from
two download providers (existing check only catches identical NVRA strings).

---

## Documented Limitations

### `--allowerasing` side effects
When a package is replaced by an artifact (obsoletes case), `--allowerasing` may
remove other packages that depend on the obsoleted package. DNF output will show
removed packages. The user is responsible for understanding this consequence.

### `file:` provider and reinstall availability
`dnf reinstall <name>` reinstalls the currently-installed version. After Command 1,
the installed version IS the artifact's version. For `file:` providers, the RPM is in
`tmt-artifact-shared` (local createrepo), which persists for the duration of the run.
So reinstall always finds the package. ✓

### Epoch handling
`Version.nvra` does **not** include epoch; `Version.nevra` does (e.g. `foo-0:1.1-1.noarch`).
`_ensure_artifacts_installed` uses `nevra` so DNF receives an unambiguous version spec
regardless of epoch. DNF accepts NEVRA format, and epoch=0 packages (the vast majority)
produce `foo-0:1.1-1.noarch` which DNF treats identically to `foo-1.1-1.noarch`.

### Unrequested artifact packages
If an artifact provider has a package that is NOT listed in any tmt install phase,
`_compute_pkgs_to_verify` will not include it in `pkgs_to_verify`, so
`_ensure_artifacts_installed` will not touch it. This is correct — tmt only force-installs
packages the test explicitly requested.

### `verify=False` does not disable force-install — wait, it does
`_ensure_artifacts_installed` is called inside `if self.data.verify:`. This means
when the user passes `--no-verify`, neither the origin check nor the force-install runs,
and bug #4838 would still be present. This is a deliberate coupling: the force-install
is considered part of the verify contract. If this behaviour needs to change in future,
`_ensure_artifacts_installed` should be moved outside the verify guard.

---

## Files to Change

| File | Change |
|---|---|
| `tmt/package_managers/__init__.py` | Add `allow_downgrade`, `allow_erasing` to `Options` |
| `tmt/package_managers/dnf.py` | Add `allow_erasing` to `DnfEngine._extra_dnf_options`; add `Dnf5Engine._extra_dnf_options` override for `allow_downgrade` |
| `tmt/steps/prepare/artifact/providers/__init__.py` | Add `is_download_provider` property to `ArtifactProvider` base class |
| `tmt/steps/prepare/artifact/__init__.py` | New `_compute_pkgs_to_verify`, new `_ensure_artifacts_installed`, simplified `_inject_verify_phase`, extended `_detect_duplicate_nvras`, updated `go()` |

---

## LecrisUT Test Matrix Coverage

All rows previously marked `?` are now resolved:

| Row type | Status |
|---|---|
| Simple install/upgrade/downgrade, single provider | ✓ Covered — S1/S2/S3 POC confirmed |
| Pre-installed same NVRA, empty swdb origin (base image) | ✓ Covered via reinstall — S4/S5 POC confirmed |
| Transitive dep downgrade (`foo-devel` → `foo`) | ✓ Covered — S6 POC confirmed (DNF5: `--allow-downgrade`; DNF4: automatic) |
| Older artifact than pre-installed (direct downgrade) | ✓ Covered — same as S3, repo priority drives it |
| Multiple providers, same package (download wins) | ✓ Covered via priority ordering in `_ensure_artifacts_installed` |
| Obsoletes (`foo-ng` vs `foo`) | ✓ Covered via `--allowerasing` — S8 POC confirmed |
| Bad artifact (cannot install) | ✓ Fails hard at order=50 before test runs — correct behaviour |
| Artifact package NOT in any require/recommends | ✓ Not touched — only `pkgs_to_verify` packages are affected |
