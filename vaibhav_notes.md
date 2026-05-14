# NVR Priority Test Cases

## Legend

- `-` not present
- `x` not installed
- `*` case not in original table
- `foo-devel` package that `Requires: foo = %{version}-%{release}`
- `foo-ng` package that `Provides: foo` + `Obsoletes: foo < ...`

## Established behavior

- Artifact repo: priority=50, system repo: priority=99 — artifact always wins on priority regardless of version
- Special artifact (local RPMs): always installed at specified version regardless of what is pre-installed
- Versions are labels for ordering: 1.1 < 1.2 < 1.4 (system) < 2.2 < 2.4

## Open design decisions (`?`)

- **Downgrade**: artifact (repo or special) version older than pre-installed (1.C.4, 2.B.3, 4.A.4, 4.B.2)
- **Unrequested packages**: artifact present for a package not in the request list (3.2, 3.3)
- **Provides/Obsoletes vs priority**: foo-ng Obsoletes interaction with artifact priority (5.B.1, 5.B.4)

---

## Section 1 — Simple package (`foo`), direct provider in system

### 1.A — No pre-installed

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 1.A.1 | foo | foo-1.4 | x | - | - | foo-1.4 |
| 1.A.2 | foo | foo-1.4 | x | foo-2.2 | - | foo-2.2 |
| 1.A.3 * | foo | foo-1.4 | x | - | foo-2.4 | foo-2.4 |
| 1.A.4 | foo | foo-1.4 | x | foo-2.2 | foo-2.4 | foo-2.4 |
| 1.A.5 | foo | foo-1.4 | x | foo-1.2 | - | foo-1.2 |
| 1.A.6 * | foo | foo-1.4 | x | - | foo-1.1 | foo-1.1 |
| 1.A.7 | foo | foo-1.4 | x | foo-1.2 | foo-1.1 | foo-1.1 |

- 1.A.3, 1.A.6: special-only cases were missing from original
- 1.A.5 (was `?`): artifact priority=50 beats system priority=99 even for an older version when nothing is pre-installed → foo-1.2

### 1.B — Pre-installed older than system (foo-1.0)

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 1.B.1 | foo | foo-1.4 | foo-1.0 | - | - | foo-1.4 |
| 1.B.2 * | foo | foo-1.4 | foo-1.0 | foo-2.2 | - | foo-2.2 |
| 1.B.3 * | foo | foo-1.4 | foo-1.0 | - | foo-2.4 | foo-2.4 |
| 1.B.4 * | foo | foo-1.4 | foo-1.0 | foo-1.2 | - | foo-1.2 |
| 1.B.5 * | foo | foo-1.4 | foo-1.0 | - | foo-1.1 | foo-1.1 |
| 1.B.6 * | foo | foo-1.4 | foo-1.0 | foo-1.2 | foo-1.1 | foo-1.1 |

- 1.B.1 (was `?`): no artifact, standard DNF upgrade from 1.0 to system version → foo-1.4
- All artifact versions (1.1, 1.2, 2.2, 2.4) are greater than pre-installed (1.0) — no downgrade concern anywhere in this group, artifact priority wins cleanly
- 1.B.4 is the notable case: artifact is older than system but newer than pre-installed — artifact priority still wins

### 1.C — Pre-installed same as system (foo-1.4)

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 1.C.1 | foo | foo-1.4 | foo-1.4 | foo-2.2 | - | foo-2.2 |
| 1.C.2 | foo | foo-1.4 | foo-1.4 | - | foo-2.4 | foo-2.4 |
| 1.C.3 * | foo | foo-1.4 | foo-1.4 | foo-2.2 | foo-2.4 | foo-2.4 |
| 1.C.4 | foo | foo-1.4 | foo-1.4 | foo-1.2 | - | ? |
| 1.C.5 | foo | foo-1.4 | foo-1.4 | - | foo-1.1 | foo-1.1 |
| 1.C.6 * | foo | foo-1.4 | foo-1.4 | foo-1.2 | foo-1.1 | foo-1.1 |

- 1.C.4 remains `?`: artifact version < pre-installed → downgrade behavior undecided

---

## Section 2 — Multiple packages (`foo, bar`)

### 2.A — Pre-installed: foo-1.0

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 2.A.1 | foo, bar | foo-1.4, bar | foo-1.0 | - | - | foo-1.4, bar |

- 2.A.1 (was `?`): foo upgrades to 1.4 from system, bar installs from system

### 2.B — Pre-installed: foo-1.4

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 2.B.1 | foo, bar | foo-1.4, bar | foo-1.4 | foo-2.2 | - | foo-2.2, bar |
| 2.B.2 | foo, bar | foo-1.4, bar | foo-1.4 | - | foo-2.4 | foo-2.4, bar |
| 2.B.3 | foo, bar | foo-1.4, bar | foo-1.4 | foo-1.2 | - | ?, bar |
| 2.B.4 | foo, bar | foo-1.4, bar | foo-1.4 | - | foo-1.1 | foo-1.1, bar |

- 2.B.1 (was `?`): artifact newer + priority → foo-2.2, bar from system
- 2.B.3 (was `?`): same downgrade question as 1.C.4 for foo; bar always comes from system

### 2.C — Pre-installed: bar only

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 2.C.1 | foo, bar | foo-1.4, bar | bar | - | - | foo-1.4, bar |

- 2.C.1 (was `?`): foo installs from system, bar already present and unchanged

---

## Section 3 — Artifact present for unrequested package (`bar` requested, `foo` in artifact)

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 3.1 | bar | foo-1.4, bar | foo-1.0 | - | - | foo-1.0, bar |
| 3.2 | bar | foo-1.4, bar | foo-1.4 | foo-2.2 | - | ? |
| 3.3 | bar | foo-1.4, bar | foo-1.4 | - | foo-2.4 | ? |

- 3.1 (was `?`): only bar requested, DNF does not touch foo → foo-1.0 stays, bar installs
- 3.2, 3.3 remain `?`: does the artifact plugin install/upgrade packages that were not explicitly requested?

---

## Section 4 — Dependency chain (`foo-devel` requires `foo = %{version}-%{release}`)

### 4.A — Both foo and foo-devel available in system repo

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 4.A.1 | foo-devel | foo-1.4, foo-devel-1.4 | foo-1.0 | - | - | foo-1.4, foo-devel-1.4 |
| 4.A.2 | foo-devel | foo-1.4, foo-devel-1.4 | foo-1.4 | foo-2.2, foo-devel-2.2 | - | foo-2.2, foo-devel-2.2 |
| 4.A.3 | foo-devel | foo-1.4, foo-devel-1.4 | foo-1.4 | - | foo-2.4, foo-devel-2.4 | foo-2.4, foo-devel-2.4 |
| 4.A.4 | foo-devel | foo-1.4, foo-devel-1.4 | foo-1.4 | foo-1.2, foo-devel-1.2 | - | ? |
| 4.A.5 | foo-devel | foo-1.4, foo-devel-1.4 | foo-1.4 | - | foo-1.1, foo-devel-1.1 | foo-1.1, foo-devel-1.1 |

- 4.A.2 (was `?`): artifact newer + priority; foo-devel-2.2 requires `foo = 2.2`, so both pulled from artifact → foo-2.2, foo-devel-2.2
- 4.A.4 remains `?`: downgrade + exact version dep creates compounded uncertainty

### 4.B — Only foo in system repo (foo-devel available only in artifact)

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 4.B.1 | foo-devel | foo-1.4 | foo-1.4 | foo-2.2, foo-devel-2.2 | - | foo-2.2, foo-devel-2.2 |
| 4.B.2 | foo-devel | foo-1.4 | foo-1.4 | foo-1.2, foo-devel-1.2 | - | ? |
| 4.B.3 | foo-devel | foo-1.4 | foo-1.4 | - | foo-1.1, foo-devel-1.1 | foo-1.1, foo-devel-1.1 |

- 4.B.2 (was `?`): same downgrade concern as 4.A.4

---

## Section 5 — Provider substitution (foo-ng: `Provides: foo`, `Obsoletes: foo`)

### 5.A — System has direct foo, artifact is foo-ng (switching provider)

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 5.A.1 | foo | foo-1.4 | x | foo-ng-2.2 | - | foo-ng-2.2 |
| 5.A.2 | foo | foo-1.4 | x | - | foo-ng-2.4 | foo-ng-2.4 |
| 5.A.3 | foo | foo-1.4 | foo-1.0 | foo-ng-2.2 | - | foo-ng-2.2 |
| 5.A.4 | foo | foo-1.4 | foo-1.0 | - | foo-ng-2.4 | foo-ng-2.4 |

- 5.A.3 (was `?`): artifact priority wins, foo-ng-2.2 installs and obsoletes foo-1.0 → foo-ng-2.2

### 5.B — System has foo-ng, artifact is direct foo (reverting provider)

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 5.B.1 | foo | foo-ng-1.4 | x | foo-1.2 | - | ? |
| 5.B.2 | foo | foo-ng-1.4 | x | - | foo-1.1 | foo-1.1 |
| 5.B.3 | foo | foo-ng-1.4 | foo-1.0 | - | - | foo-ng-1.4 |
| 5.B.4 | foo | foo-ng-1.4 | foo-1.4 | foo-1.2 | - | ? |
| 5.B.5 | foo | foo-ng-1.4 | foo-1.4 | - | foo-1.1 | foo-1.1 |

- 5.B.1 (was `?`): does foo-ng-1.4's `Obsoletes: foo` block installing artifact's foo-1.2 despite priority=50?
- 5.B.3 (was `?`): no artifact, system's foo-ng-1.4 provides and obsoletes foo → replaces foo-1.0 → foo-ng-1.4
- 5.B.4 (was `?`): downgrade + Obsoletes combination, doubly undecided

### 5.C — System has foo-ng, artifact is also foo-ng (upgrading the provider) *

| # | Request | System | Pre-installed | Artifact | Special | Expected |
|---|---------|--------|---------------|----------|---------|----------|
| 5.C.1 * | foo | foo-ng-1.4 | x | foo-ng-2.2 | - | foo-ng-2.2 |
| 5.C.2 * | foo | foo-ng-1.4 | x | - | foo-ng-2.4 | foo-ng-2.4 |

- Entire group was missing from original — tests upgrading an already-ng provider via artifact


---


  Where the Design Works

  The install --allow-downgrade + reinstall two-command pattern correctly handles:

  Case: Not installed (recommends skipped)
  install --allow-downgrade: installs from artifact repo
  reinstall: —
  Verdict: ✓
  ────────────────────────────────────────
  Case: Same NVRA, <unknown> origin (pre-built image)
  install --allow-downgrade: no-op
  reinstall: reinstalls, fixes origin
  Verdict: ✓
  ────────────────────────────────────────
  Case: Same NVRA from system repo
  install --allow-downgrade: no-op
  reinstall: reinstalls from artifact (priority wins)
  Verdict: ✓
  ────────────────────────────────────────
  Case: Older version installed → artifact is newer
  install --allow-downgrade: upgrades
  reinstall: —
  Verdict: ✓
  ────────────────────────────────────────
  Case: Newer version installed → artifact is older
  install --allow-downgrade: downgrades
  reinstall: —
  Verdict: ✓ (single provider)

  ---
  Where the Design Fails or Is Uncertain

  Failure 1: Multiple providers with the same package at different versions (rows 3, 5)

  LecrisUT's table:
  Row 3: Request=foo, art=foo-2.2, art_v=foo-2.4  → Expected: foo-2.4
  Row 5: Request=foo, art=foo-1.2, art_v=foo-1.1  → Expected: foo-1.1

  The design collects NVRAs from all providers:
  nvras = [foo-2.2-1.fc42.x86_64, foo-2.4-1.fc42.x86_64]
  dnf install --allow-downgrade foo-2.2-1.fc42.x86_64 foo-2.4-1.fc42.x86_64

  DNF rejects this — two versions of the same package in one transaction is a conflict. The existing
  _detect_duplicate_nvras only catches the same exact NVRA string, not different versions of the same package name.

  This is a hard crash, not a graceful failure.

  ---
  Failure 2: Obsoletes — foo-ng replaces foo or vice versa (rows 30–36)

  Row 31: Request=foo, sys=foo-ng-1.4 (Provides: foo, Obsoletes: foo < 1.4),
          pre=x, art_v=foo-1.1 → Expected: foo-1.1

  foo-ng-1.4 obsoletes foo < 1.4. Installing foo-1.1 (which is < 1.4) is blocked by DNF regardless of
  --allow-downgrade. You would need --allowerasing to remove foo-ng and replace it with foo-1.1.

  --allowerasing is risky — it can silently remove unrelated packages that depend on foo-ng.

  Row 30: Request=foo, sys=foo-ng-1.4 (Provides: foo), pre=x, art=foo-1.2, art_v=-
  Similar problem in reverse: system provides foo via foo-ng, artifact has the old-style foo-1.2. Priority won't help —
   DNF honours obsoletes before priority.

  The design has no answer for obsoletes cases.

  ---
  Failure 3: Transitive dependency downgrade — uncertain DNF behaviour (row 24, 27)

  Row 24: Request=foo-devel, pre=foo-1.4, art_v=foo-1.1 + foo-devel-1.1
          foo-devel-1.1 has: Requires: foo = 1.1  ← strict version pin

  The design only puts foo-devel in nvras (because only foo-devel is in require, not foo):
  dnf install --allow-downgrade foo-devel-1.1-1.fc42.x86_64

  For this to work, DNF must also downgrade foo from 1.4 to 1.1 as a transitive dep. The question is whether
  --allow-downgrade propagates to the entire transaction or only to the explicitly named package. This needs
  experimental verification — behaviour may differ between DNF4 and DNF5.

  ---
  Uncertainty 4: "Artifact" vs "Artifact (verify)" — distinction not in the data model

  LecrisUT's table has two separate columns:
  - Artifact = a provider making packages available (e.g. for dependency satisfaction)
  - Artifact (verify) = the build actually under test, must come from this exact repo

  Several rows mark "?" under "Artifact" column, especially when the artifact version is older than the system version:

  Row 4:  art=foo-1.2 (older than sys foo-1.4), art_v=- → ?
  Row 9:  pre=foo-1.4, art=foo-1.2, art_v=-            → ?

  The expected outcome is uncertain because it's unclear whether an "Artifact" (non-verify) provider should force a
  downgrade when it has an older version. The current design force-installs from ALL providers indiscriminately. This
  may be too aggressive for non-verify artifacts.

  tmt's current data model has no way to express this distinction — both types are just entries in self.data.provide.

  ---
  Failure 5: Bad artifact crashes at order=50, before requires/recommends (rows 37–55)

  Row 37: art=foo-2.2(bad), art_v=- → ?
  Row 38: art=-, art_v=foo-2.4(bad) → FAIL

  If dnf install --allow-downgrade foo-2.2(bad)-nvra fails at order=50, the exception propagates before
  requires/recommends (70/75) ever run. For "Artifact (verify)", hard failure is correct. But for a bad "Artifact"
  (non-verify) dependency provider, should it fall back to the system repo? The design has no fallback mechanism.

  ---
  Summary Table

  ┌─────────────────────────────────────────────────────┬────────────────────────────────┐
  │                      Scenario                       │       Design handles it?       │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Package not installed (recommends skipped)          │ ✓                              │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Pre-installed same NVRA, wrong origin               │ ✓                              │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Upgrade (artifact newer than installed)             │ ✓                              │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Downgrade (artifact older, single provider)         │ ✓                              │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Two providers with same package, different versions │ ✗ Hard crash                   │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Obsoletes: foo-ng vs foo                            │ ✗ DNF blocks it                │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Transitive dep downgrade (foo-devel needs foo=1.1)  │ ? Need to verify DNF behaviour │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Artifact vs. non-verify artifact distinction        │ ? Not modelled                 │
  ├─────────────────────────────────────────────────────┼────────────────────────────────┤
  │ Bad artifact, fallback vs hard fail                 │ ?                              │
  └─────────────────────────────────────────────────────┴────────────────────────────────┘

  ---
  Clarifying Questions

  Before finalising the plan to show people, I need answers to these:

  Q1 — Scope of the initial fix:
  Is this solution meant to fix only the concrete reproducer in #4838 (single artifact provider, vim-minimal
  pre-installed from base image, no obsoletes), or does it need to cover the full LecrisUT matrix from the start?

  Q2 — "Artifact" vs "Artifact (verify)" distinction:
  In LecrisUT's table the two columns suggest different behaviour. Is this a future data model change (two modes in
  provide:) or is the intent that every entry in provide: is a "verify" provider? This determines whether force-install
   should apply to ALL providers or only a subset.

  Q3 — Multi-provider, same package (rows 3, 5):
  If two artifact providers both contain foo at different versions, should this be a hard error at validation time
  (extend _detect_duplicate_nvras to catch same package name, not just same NVRA)? Or should one provider take priority
   (if so, which — and by what rule)?

  Q4 — Obsoletes in scope?
  Rows 30–36 require --allowerasing on top of --allow-downgrade. Is handling foo-ng ↔ foo replacement in scope for this
   fix, or explicitly out of scope and documented as a known limitation?

  Q5 — DNF transitive dep downgrade:
  Has anyone tested whether dnf install --allow-downgrade foo-devel-1.1-nvra automatically downgrades foo from 1.4 →
  1.1 to satisfy Requires: foo = 1.1? Behaviour may differ between DNF4 and DNF5. This determines whether row 24/27
  cases work without also adding foo explicitly to the install command.

  Q6 — LecrisUT's --from-repo suggestion:
  He mentioned dnf install --from-repo=tmt-artifact-shared foo-nvra as a way to guarantee origin without needing
  reinstall. Is --from-repo available in DNF4, or is it DNF5-only? If DNF5-only, does the design need a separate path
  for DNF4?
