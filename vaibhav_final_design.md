Now I have everything. Let me think through this carefully before writing.

**Key architectural observations:**

1. Fix 1 (`check_first=True` per-package loop) and Fix 2 (artifact enforcement) touch *different methods* in `dnf.py` — `_construct_install_script` vs `_extra_dnf_options` — but share the `Options` class additions. They belong in one PR.

2. The artifact plugin uses `check_first=False`, so Fix 1's loop never fires on the artifact path. These are genuinely orthogonal — Fix 1 doesn't help #4838, and Fix 2 doesn't help the `best=True` upgrade bug.

3. The `reinstall` path uses `&&` (run only if all present), not `||`. It has no equivalent bug and needs no change.

4. The `from_repo` nuance: for packages installed via `rpm -i` (base images), DNF5 resolves `from_repo` dynamically against configured repos — which means even before reinstall, it *looks* like the artifact repo owns the package. But this is unreliable (disappears if the repo is unconfigured). `dnf reinstall` writes a permanent swdb entry. The reinstall step is required for reliable verification.

Here's the unified design:

---

## Comment 3: Design

### Two problems, one changeset

**P1** — When any package is missing from a `requires:` set, the current logic runs `dnf install` on the entire set. On RHEL/CentOS (DNF4, `best=True`), already-installed packages get silently upgraded as a side effect.

**P2** (issue #4838) — The artifact plugin adds repos and enumerates packages, but does not guarantee they are installed at the exact artifact version. A package already on the system at the wrong version, or installed via `rpm -i` without a DNF swdb entry, passes the current checks undetected and runs the test against the wrong build.

These are bugs at different layers but share the same code change window. Fix 1 is foundational; Fix 2 builds on the new `Options` fields Fix 1 introduces.

---

### Fix 1 — Per-package presence check (`tmt/package_managers/dnf.py`)

The `_construct_install_script` method in `DnfEngine` currently generates:

```bash
rpm -q --whatprovides A B C D || dnf install A B C D
```

When any package is missing, the entire set goes to `dnf install`. Packages that are already installed reach DNF, and with `best=True` they can be silently upgraded. Replace with a per-package loop that only passes missing packages to DNF:

```bash
_tmt_missing=()
for _tmt_pkg in A B C D; do
    rpm -q --whatprovides "$_tmt_pkg" &>/dev/null || _tmt_missing+=("$_tmt_pkg")
done
[[ ${#_tmt_missing[@]} -eq 0 ]] || dnf install "${_tmt_missing[@]}"
```

This is a **single SSH execution** — the rpm-q calls are local RPM DB lookups on the guest, not network calls. tmt uses `/bin/bash` (`DEFAULT_SHELL`), so array syntax is safe. Packages already installed never reach `dnf install`, making `best=True` vs `best=False` irrelevant.

The rewritten method, restructured to make both paths explicit:

```python
# tmt/package_managers/dnf.py
def _construct_install_script(
    self, *installables: Installable, options: Optional[Options] = None
) -> ShellScript:
    options = options or Options()
    extra_options = self._extra_dnf_options(options)
    install_cmd = (
        f'{self.command.to_script()} install '
        f'{self.options.to_script()} {extra_options}'
    )

    if not options.check_first:
        # check_first=False: used by artifact plugin — unconditional, no loop
        return ShellScript(
            f'{install_cmd} {" ".join(escape_installables(*installables))}'
        )

    # check_first=True: per-package presence check, install only missing packages
    pkgs = " ".join(escape_installables(*installables))
    return ShellScript(
        f'_tmt_missing=(); '
        f'for _tmt_pkg in {pkgs}; do '
        f'  rpm -q --whatprovides "$_tmt_pkg" &>/dev/null || _tmt_missing+=("$_tmt_pkg"); '
        f'done; '
        f'[[ ${{#_tmt_missing[@]}} -eq 0 ]] || {install_cmd} "${{_tmt_missing[@]}}"'
    )
```

`skip_missing` (`--skip-broken`) is already part of `extra_options` and flows into `install_cmd` unchanged. `check_first=False` callers — including the artifact plugin — are unaffected.

---

### Fix 2 — Artifact version enforcement (`tmt/steps/prepare/artifact/__init__.py`, #4838)

**The two-command pattern**, run at order=50 inside `_ensure_artifacts_installed`:

```
# Command 1: install exact artifact NVRA (handles all version/origin states except same-NVRA)
dnf install [--allow-downgrade] --allowerasing <nvra1> <nvra2> ...

# Command 2: fix swdb origin for packages already on the system at the exact NVRA
dnf reinstall <pkg-name1> <pkg-name2> ...
```

Command 1 uses explicit NEVRAs (epoch-qualified) so DNF has no ambiguity about the target version. Command 2 is needed because `dnf install <nvra>` for an already-installed package at that exact NVRA is a no-op — it does not update the swdb origin. `dnf reinstall` writes a new swdb entry with the artifact repo as origin, which is what `verify-installation` checks.

**DNF4 vs DNF5:**

|                          | DNF4 (RHEL)                         | DNF5 (Fedora)                       |
| ------------------------ | ----------------------------------- | ----------------------------------- |
| Direct downgrade         | automatic — repo priority drives it | automatic — repo priority drives it |
| Transitive dep downgrade | automatic                           | requires `--allow-downgrade`        |
| `--allow-downgrade` flag | does not exist                      | required for transitive deps        |
| `--allowerasing`         | supported                           | supported                           |

`--allow-downgrade` is added via a new `Dnf5Engine._extra_dnf_options` override. It is not added in `DnfEngine` because the flag does not exist in DNF4.

**Full version/origin state coverage:**

| State                                                     | Command 1                                                   | Command 2                                               | Final origin |
| --------------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------- | ------------ |
| Not installed                                             | installs from artifact repo                                 | no-op                                                   | ✓            |
| Older version                                             | upgrades to artifact NVRA                                   | no-op                                                   | ✓            |
| Newer version                                             | downgrades to artifact NVRA (repo priority)                 | no-op                                                   | ✓            |
| Same NVRA, correct swdb origin                            | no-op                                                       | no-op                                                   | ✓            |
| Same NVRA, no swdb entry (`rpm -i`, base image)           | no-op                                                       | reinstalls → writes swdb entry                          | ✓            |
| Same NVRA, wrong swdb origin                              | no-op                                                       | reinstalls from artifact (priority wins) → updates swdb | ✓            |
| `foo-ng` installed (`Obsoletes: foo`), artifact has `foo` | `--allowerasing` removes `foo-ng`, installs `foo`           | no-op                                                   | ✓            |
| `foo-devel-1.1` requires `foo = 1.1`, `foo-1.4` installed | DNF5: `--allow-downgrade` downgrades `foo`; DNF4: automatic | no-op                                                   | ✓            |

**Provider priority:** download providers (`koji.build:`, `brew.build:`, `file:`, `copr.build:`) are processed before discover-only providers (`repository-file:`, `repository-url:`). If both have the same package, the download provider wins. Two download providers claiming the same package name is caught at startup by extended `_detect_duplicate_nvras` — a hard error before any install attempt.

---

### New `Options` fields

Both fixes share additions to the `Options` container:

```python
# tmt/package_managers/__init__.py
@container
class Options:
    # ... existing fields ...
    allow_downgrade: bool = False   # DNF5 only: --allow-downgrade for transitive dep downgrades
    allow_erasing: bool = False     # DNF4 + DNF5: --allowerasing for obsoletes replacement
```

`allow_erasing` → `DnfEngine._extra_dnf_options` (both engines inherit it).
`allow_downgrade` → `Dnf5Engine._extra_dnf_options` override only (flag does not exist in DNF4).

The artifact plugin uses `Options(check_first=False, allow_downgrade=True, allow_erasing=True)`. The regular install path uses the default `Options(check_first=True)` — `allow_downgrade` and `allow_erasing` are never set on that path.

---

### Execution flow (end-to-end)

```
order=50  prepare/artifact
          ├── init providers
          ├── _detect_duplicate_nvras (extended: also catch same pkg name
          │   from two download providers — hard error at startup)
          ├── fetch_contents + contribute_to_shared_repo
          ├── createrepo + install .repo files on guest
          ├── enumerate_artifacts(guest) + save_artifacts_metadata()
          │
          └── if self.data.verify:
              ├── _compute_pkgs_to_verify(providers, guest)
              │     resolve_provides(pkg_names, provider_repo_ids)
              │     intersect with artifact.version.name
              │     → dict[pkg_name → {repo_ids}]
              │
              ├── _ensure_artifacts_installed(providers, pkgs_to_verify, guest)
              │     collect NEVRAs: download providers first, discover-only fills gaps
              │
              │     Command 1  Options(check_first=False, allow_downgrade=True, allow_erasing=True)
              │       DNF5: dnf5 install --allow-downgrade --allowerasing <nevra ...>
              │       DNF4: dnf  install --allowerasing <nevra ...>
              │       → handles all version states + obsoletes replacement
              │
              │     Command 2  Options(check_first=False)
              │       dnf reinstall <pkg-name ...>
              │       → fixes swdb origin for same-NVRA packages (base image, wrong origin)
              │
              └── _inject_verify_phase(pkgs_to_verify) → order=79

order=70  requires install  Options(check_first=True)  ← Fix 1 loop fires here
          per-package rpm-q: artifact packages pass (already at correct NVRA from order=50)
          _tmt_missing contains only genuinely absent packages
          dnf install called only for those

order=75  recommends install  (same as order=70)

order=79  verify-installation
          get_package_origin({foo, foo-devel, ...})
          swdb entry written by order=50 reinstall → from_repo = artifact repo → PASS
```

---

### Affected files

| File                                               | Change                                                                                                                                                                               |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tmt/package_managers/__init__.py`                 | Add `allow_downgrade`, `allow_erasing` to `Options`                                                                                                                                  |
| `tmt/package_managers/dnf.py`                      | Rewrite `_construct_install_script` with per-package loop; add `allow_erasing` to `DnfEngine._extra_dnf_options`; add `Dnf5Engine._extra_dnf_options` override for `allow_downgrade` |
| `tmt/steps/prepare/artifact/providers/__init__.py` | Add `is_download_provider: bool = False` to `ArtifactProvider`; download provider subclasses override with `True`                                                                    |
| `tmt/steps/prepare/artifact/__init__.py`           | New `_compute_pkgs_to_verify`, `_ensure_artifacts_installed`; extended `_detect_duplicate_nvras`; simplified `_inject_verify_phase`; updated `go()`                                  |

---

### What we deliberately do not do

- **No `--best` on the command line** — overrides sysadmin configuration
- **No per-package `dnf install` calls** — the loop is rpm-q only; the actual install is one DNF invocation
- **No change to `_construct_reinstall_script`** — it uses `&&` (run only when all packages present), which is correct; it has no equivalent bug
- **`update-system: true`** (opt-in upgrade via `prepare: how: feature`) — deferred; the fix does not run `dnf upgrade` by default

**Documented limitation:** `_ensure_artifacts_installed` is guarded by `if self.data.verify:`. When `--no-verify` is passed, artifact packages are not force-installed. This is intentional — force-install is considered part of the verify contract. If this needs to change, `_ensure_artifacts_installed` moves outside the verify guard.

---

### Test matrix

| Test | What it verifies                                                      | Addressed by   |
| ---- | --------------------------------------------------------------------- | -------------- |
| T1   | All installed → no dnf call                                           | Fix 1          |
| T2   | All missing → all installed                                           | Fix 1          |
| T3   | One missing → only missing installed; no upgrade of installed         | Fix 1          |
| T4   | Virtual provides respected in per-package loop                        | Fix 1          |
| T5   | `skip_missing` + partial set                                          | Fix 1          |
| T6   | Opt-in "ensure latest"                                                | Future feature |
| T7   | `best=True` on RHEL → same result as Fedora                           | Fix 1          |
| T8   | Transitive dep downgrade (DNF5: `--allow-downgrade`; DNF4: automatic) | Fix 2          |
| T9   | Obsoletes (`foo-ng` ↔ `foo`): `--allowerasing`                        | Fix 2          |
| T10  | Two download providers with same package: validation error at startup | Fix 2          |
