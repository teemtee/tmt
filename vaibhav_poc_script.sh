#!/bin/bash
# ============================================================================
# POC script: verify DNF install/downgrade/reinstall behaviour
# for tmt artifact plugin issue #4838
#
# Verifies the two-command pattern:
#   Cmd 1: dnf install [--allow-downgrade] [--allowerasing] <nvra>
#   Cmd 2: dnf reinstall <pkg-name>
#
# Scenarios match the POC results table in vaibhav_design.md.
#
# Requirements:
#   - Run as root (or with sudo) inside a container/VM
#   - rpm-build, createrepo_c  (installed automatically if missing)
#   - Fedora 41/42 for DNF5 tests, AlmaLinux/RHEL 9 for DNF4 tests
#
# Usage:
#   sudo bash vaibhav_poc_script.sh
# ============================================================================

set -euo pipefail

# ── Colour output ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; NC='\033[0m'
PASS_COUNT=0; FAIL_COUNT=0; SKIP_COUNT=0

# Fix: Avoid ((VAR++)) because if VAR is 0, the expression returns exit code 1, which kills the script under set -e
pass()   { echo -e "${GREEN}[PASS]${NC} $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail()   { echo -e "${RED}[FAIL]${NC} $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
skip()   { echo -e "${YELLOW}[SKIP]${NC} $*"; SKIP_COUNT=$((SKIP_COUNT + 1)); }
header() { echo; echo -e "${BOLD}─────────────────────────────────────────────────${NC}"; \
           echo -e "${BOLD}  $*${NC}"; \
           echo -e "${BOLD}─────────────────────────────────────────────────${NC}"; }

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || { echo "ERROR: run as root or with sudo"; exit 1; }

# ── Detect DNF ────────────────────────────────────────────────────────────────
if command -v dnf5 &>/dev/null; then
    DNF=dnf5; DNF_VER=5
elif command -v dnf &>/dev/null; then
    DNF=dnf; DNF_VER=4
else
    echo "ERROR: neither dnf5 nor dnf found"; exit 1
fi
echo "=== Using: $DNF  (DNF version $DNF_VER) ==="

# ── Install build prerequisites ───────────────────────────────────────────────
for pkg in rpm-build createrepo_c; do
    rpm -q "$pkg" &>/dev/null || { echo "Installing $pkg..."; $DNF install -y "$pkg" &>/dev/null; }
done

# ── Working directories ───────────────────────────────────────────────────────
WORK=$(mktemp -d /tmp/poc-artifact-XXXXXX)
BUILD="$WORK/rpmbuild"
SYSTEM_REPO="$WORK/system-repo"
ARTIFACT_REPO="$WORK/artifact-repo"
SYSTEM_REPO_FILE=/etc/yum.repos.d/poc-system-test.repo
ARTIFACT_REPO_FILE=/etc/yum.repos.d/poc-artifact-test.repo

echo "Working dir: $WORK"

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup_all() {
    echo; echo "=== Cleaning up ==="
    rpm -e foo foo-devel foo-ng 2>/dev/null || true
    rm -f "$SYSTEM_REPO_FILE" "$ARTIFACT_REPO_FILE"
    $DNF clean all &>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup_all EXIT

mkdir -p "$BUILD/SPECS" "$SYSTEM_REPO" "$ARTIFACT_REPO"

# ── RPM spec helper ───────────────────────────────────────────────────────────
write_spec() {
    # write_spec <specfile> <name> <version> <release> [extra-header-lines...]
    local specfile="$1" name="$2" ver="$3" rel="$4"; shift 4
    cat > "$specfile" <<EOF
Name:       $name
Version:    $ver
Release:    $rel
Summary:    Test package $name $ver
License:    MIT
BuildArch:  noarch
$*

%description
Test package $name-$ver-$rel for tmt artifact POC.

%install

%files

%changelog
EOF
}

# ── Build all RPMs ────────────────────────────────────────────────────────────
header "Building test RPMs"

# foo at 1.1, 1.2, 1.4, 2.2, 2.4
for ver in 1.1 1.2 1.4 2.2 2.4; do
    write_spec "$BUILD/SPECS/foo-${ver}.spec" foo "$ver" 1
    rpmbuild --define "_topdir $BUILD" -bb "$BUILD/SPECS/foo-${ver}.spec" &>/dev/null
done

# foo-devel at same versions — strict version pin on foo
for ver in 1.1 1.2 1.4 2.2 2.4; do
    write_spec "$BUILD/SPECS/foo-devel-${ver}.spec" foo-devel "$ver" 1 \
        "Requires:   foo = ${ver}-1"
    rpmbuild --define "_topdir $BUILD" -bb "$BUILD/SPECS/foo-devel-${ver}.spec" &>/dev/null
done

# foo-ng-1.4 — Provides: foo, Obsoletes: foo < 1.4
write_spec "$BUILD/SPECS/foo-ng-1.4.spec" foo-ng 1.4 1 \
    "Provides:   foo = 1.4-1
Obsoletes:  foo < 1.4"
rpmbuild --define "_topdir $BUILD" -bb "$BUILD/SPECS/foo-ng-1.4.spec" &>/dev/null

# foo-ng-2.2 — Provides: foo, Obsoletes: foo < 2.2
write_spec "$BUILD/SPECS/foo-ng-2.2.spec" foo-ng 2.2 1 \
    "Provides:   foo = 2.2-1
Obsoletes:  foo < 2.2"
rpmbuild --define "_topdir $BUILD" -bb "$BUILD/SPECS/foo-ng-2.2.spec" &>/dev/null

RPM_DIR=$(find "$BUILD/RPMS" -name "*.rpm" -exec dirname {} \; | sort -u | head -1)
echo "Built RPMs in: $RPM_DIR"
find "$RPM_DIR" -name "*.rpm" -exec basename {} \; | sort

# ── System repo — has foo-1.4 and foo-devel-1.4 ───────────────────────────────
cp "$RPM_DIR"/foo-1.4-1.noarch.rpm     "$SYSTEM_REPO/"
cp "$RPM_DIR"/foo-devel-1.4-1.noarch.rpm "$SYSTEM_REPO/"
createrepo "$SYSTEM_REPO" -q

cat > "$SYSTEM_REPO_FILE" <<EOF
[poc-system-test]
name=POC System Repo (test)
baseurl=file://$SYSTEM_REPO
enabled=1
gpgcheck=0
priority=99
EOF

# ── Test helpers ──────────────────────────────────────────────────────────────

# Populate artifact repo with given basenames (without .rpm suffix) and write .repo file
set_artifact() {
    rm -f "$ARTIFACT_REPO"/*.rpm
    for name in "$@"; do
        cp "$RPM_DIR/${name}.noarch.rpm" "$ARTIFACT_REPO/"
    done
    createrepo "$ARTIFACT_REPO" -q
    cat > "$ARTIFACT_REPO_FILE" <<EOF
[poc-artifact-test]
name=POC Artifact Repo (test)
baseurl=file://$ARTIFACT_REPO
enabled=1
gpgcheck=0
priority=50
EOF
    $DNF clean all &>/dev/null || true
}

clear_artifact() {
    rm -f "$ARTIFACT_REPO_FILE" "$ARTIFACT_REPO"/*.rpm 2>/dev/null || true
    $DNF clean all &>/dev/null || true
}

# Remove test packages (ignore errors if not installed)
# Must use DNF (not rpm -e) so that the DNF5 swdb entry is cleared — rpm -e only
# removes from the RPM database, leaving a stale swdb entry that from_repo queries
# will continue to return even after rpm -i reinstalls the same package.
remove_pkgs() { $DNF remove -y "$@" &>/dev/null || true; }

# Install directly via rpm (no repo origin — simulates pre-installed image package)
install_direct() {
    rpm -i --force "$RPM_DIR/${1}.noarch.rpm"
}

# Query installed version as "ver-rel"
installed_ver() {
    rpm -q --qf '%{VERSION}-%{RELEASE}' "$1" 2>/dev/null || echo "not-installed"
}

# Query from_repo for an installed package
#   DNF5: returns "<hash>" for base-image packages, "<repo-id>" for dnf-installed ones
#   DNF4: returns "@System" or "<repo-id>"
from_repo() {
    if [[ $DNF_VER -eq 5 ]]; then
        dnf5 repoquery --installed --qf '%{from_repo}' "$1" 2>/dev/null | tail -n 1 || true
    else
        dnf repoquery --installed --qf '%{from_repo}' "$1" 2>/dev/null | tail -n 1 || true
    fi
}

# Check installed version
assert_ver() {
    local label="$1" pkg="$2" expected="$3"
    local got; got=$(installed_ver "$pkg")
    if [[ "$got" == "$expected" ]]; then
        pass "$label → $pkg version: $got"
    else
        fail "$label → $pkg version: expected=$expected got=$got"
    fi
}

# Check that from_repo contains the expected repo ID
assert_origin() {
    local label="$1" pkg="$2" expected_repo="$3"
    local got; got=$(from_repo "$pkg") || true
    if [[ "$got" == *"$expected_repo"* ]]; then
        pass "$label → $pkg origin contains '$expected_repo' (full: $got)"
    else
        fail "$label → $pkg origin: expected to contain '$expected_repo', got='$got'"
    fi
}

# Check that from_repo does NOT contain the expected repo ID (still on image/unknown origin)
assert_not_origin() {
    local label="$1" pkg="$2" bad_repo="$3"
    local got; got=$(from_repo "$pkg") || true
    if [[ "$got" != *"$bad_repo"* ]]; then
        pass "$label → $pkg origin NOT '$bad_repo' (still: $got)"
    else
        fail "$label → $pkg origin: should NOT be '$bad_repo', got='$got'"
    fi
}

# Run any dnf subcommand with output suppressed; dump last 20 lines only on failure
dnf_cmd() {
    local log; log=$(mktemp)
    if ! $DNF "$@" >"$log" 2>&1; then
        echo "  [dnf $* — FAILED, last 20 lines:]"
        tail -n 20 "$log"
        rm -f "$log"
        return 1
    fi
    rm -f "$log"
}

# Wrapper: dnf install restricted to poc-* repos only
dnf_install() {
    dnf_cmd install -y --repo='poc-*' "$@"
}

# Wrapper: dnf reinstall restricted to poc-* repos only
dnf_reinstall() {
    dnf_cmd reinstall -y --repo='poc-*' "$@"
}

# ── DNF5 SCENARIOS ────────────────────────────────────────────────────────────

header "DNF5: Scenario 1 — Package NOT installed → installs from artifact repo"
# Expected: installs foo-1.1 from artifact repo (priority=50 wins over system priority=99)
remove_pkgs foo
set_artifact foo-1.1-1
echo "CMD: $DNF install foo-1.1-1.noarch --repo='poc-*'"
dnf_install foo-1.1-1.noarch
assert_ver     "S1" foo "1.1-1"
assert_origin  "S1" foo "poc-artifact-test"
remove_pkgs foo

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF5: Scenario 2 — Installed at OLDER version (1.1) → upgrades to artifact 2.2"
remove_pkgs foo
install_direct foo-1.1-1
assert_ver "S2 pre-install" foo "1.1-1"
set_artifact foo-2.2-1
echo "CMD: $DNF install foo-2.2-1.noarch --repo='poc-*'"
dnf_install foo-2.2-1.noarch
assert_ver     "S2" foo "2.2-1"
assert_origin  "S2" foo "poc-artifact-test"
remove_pkgs foo

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF5: Scenario 3 — Installed at NEWER version (2.4) → downgrades to artifact 1.1"
# Key result: specifying the explicit NVRA causes a downgrade; no --allow-downgrade needed
# (--allow-downgrade is only for TRANSITIVE dep downgrades in DNF5)
remove_pkgs foo
install_direct foo-2.4-1
assert_ver "S3 pre-install" foo "2.4-1"
set_artifact foo-1.1-1
echo "CMD: $DNF install foo-1.1-1.noarch --repo='poc-*'"
dnf_install foo-1.1-1.noarch
assert_ver     "S3" foo "1.1-1"
assert_origin  "S3" foo "poc-artifact-test"
remove_pkgs foo

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF5: Scenario 4 — Same NVRA, 'unknown' origin (pre-built image) → install is NO-OP"
# Simulate image-preinstalled package: use rpm -i directly (no repo in RPMDB)
# Expected: dnf install sees it as already installed, does NOT change origin
# NOTE: clear_artifact must come before install_direct — DNF5 resolves %{from_repo}
# dynamically against currently-configured repos, so any active repo would cause
# from_repo to show that repo even for packages installed via bare rpm -i.
remove_pkgs foo
clear_artifact
install_direct foo-1.1-1
echo "=== Before install: from_repo=$(from_repo foo) (should be unknown) ==="
assert_not_origin  "S4 origin before repo config" foo "poc-artifact-test"
set_artifact foo-1.1-1
echo "CMD: $DNF install foo-1.1-1.noarch --repo='poc-*'"
dnf_install foo-1.1-1.noarch || true  # may exit 0 with "already installed" message
assert_ver  "S4 version unchanged" foo "1.1-1"
# DNF5: from_repo is dynamic — once artifact repo is configured it resolves immediately;
# the no-op-for-origin property is only meaningful before set_artifact (checked above).
echo "=== After install: from_repo=$(from_repo foo) ==="

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF5: Scenario 5 — Same NVRA, 'unknown' origin → REINSTALL fixes origin"
# Continuing from Scenario 4 state (foo-1.1 installed with unknown origin, artifact repo active)
echo "CMD: $DNF reinstall foo --repo='poc-*'"
dnf_reinstall foo
assert_ver     "S5 version unchanged" foo "1.1-1"
assert_origin  "S5 origin fixed" foo "poc-artifact-test"
echo "=== After reinstall: from_repo=$(from_repo foo) (should be poc-artifact-test) ==="
remove_pkgs foo
clear_artifact

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF5: Scenario 6 — Transitive dep downgrade (foo-devel-1.1 requires foo=1.1, foo-1.4 installed)"
# foo-devel-1.1 has: Requires: foo = 1.1-1
# Artifact repo has: foo-1.1, foo-devel-1.1
# Pre-installed: foo-1.4 (from system / direct install)
# Expected: --allow-downgrade flag causes foo to be downgraded from 1.4 → 1.1 as dep
remove_pkgs foo foo-devel
install_direct foo-1.4-1
assert_ver "S6 pre-install foo" foo "1.4-1"
set_artifact foo-1.1-1 foo-devel-1.1-1
echo "CMD: $DNF install --allow-downgrade foo-devel-1.1-1.noarch --repo='poc-*'"
if [[ $DNF_VER -eq 5 ]]; then
    dnf_cmd install -y --allow-downgrade --repo='poc-*' foo-devel-1.1-1.noarch
    assert_ver     "S6 foo-devel version" foo-devel "1.1-1"
    assert_ver     "S6 foo downgraded"    foo       "1.1-1"
    assert_origin  "S6 foo-devel origin"  foo-devel "poc-artifact-test"
    assert_origin  "S6 foo origin"        foo       "poc-artifact-test"
else
    # DNF4: --allow-downgrade does not exist; transitive downgrade should happen automatically
    echo "CMD: $DNF install foo-devel-1.1-1.noarch --repo='poc-*'"
    dnf_cmd install -y --repo='poc-*' foo-devel-1.1-1.noarch || true
    assert_ver "S6 (DNF4) foo-devel version" foo-devel "1.1-1"
    assert_ver "S6 (DNF4) foo downgraded"    foo       "1.1-1"
fi
remove_pkgs foo foo-devel
clear_artifact

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF5: Scenario 7 — --from-repo / --repo flag availability"
# DNF5: The equivalent is the global --repo=<id> flag (not --from-repo)
# DNF4: Same global --repo=<id> flag
echo "=== Testing $DNF install --repo=<id> foo syntax ==="
remove_pkgs foo
set_artifact foo-1.1-1
if [[ $DNF_VER -eq 5 ]]; then
    # DNF5 uses global --repo flag; --from-repo does NOT exist
    echo "CMD: $DNF install --repo=poc-artifact-test foo-1.1-1.noarch"
    if dnf_cmd install -y --repo=poc-artifact-test foo-1.1-1.noarch; then
        pass "S7 (DNF5) --repo=<id> flag accepted and works"
    else
        fail "S7 (DNF5) --repo=<id> flag rejected"
    fi
    echo "---"
    echo "CMD: $DNF install --from-repo=poc-artifact-test foo (DNF5 accepts this as an alias for --repo)"
    if dnf_cmd install -y --from-repo=poc-artifact-test foo; then
        pass "S7 --from-repo accepted in DNF5 (works as alias for --repo)"
    else
        fail "S7 --from-repo rejected in DNF5 (expected it to work as --repo alias)"
    fi
else
    # DNF4 equivalent: --repo=<id>
    echo "CMD: $DNF install --repo=poc-artifact-test foo-1.1-1.noarch"
    if dnf_cmd install -y --repo=poc-artifact-test foo-1.1-1.noarch; then
        pass "S7 (DNF4) --repo=<id> flag accepted and works"
    else
        fail "S7 (DNF4) --repo=<id> flag rejected"
    fi
fi
remove_pkgs foo
clear_artifact

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF5: Scenario 8 — Obsoletes: foo-ng-1.4 installed, install artifact foo-1.1"
# foo-ng-1.4: Provides foo=1.4, Obsoletes foo < 1.4
# Without --allowerasing: dnf refuses to install foo-1.1 (obsoleted by foo-ng-1.4)
# With --allowerasing: dnf removes foo-ng-1.4 and installs foo-1.1
remove_pkgs foo foo-ng
set_artifact foo-ng-1.4-1 foo-1.1-1
dnf_install foo-ng-1.4-1.noarch
assert_ver "S8 pre-install foo-ng" foo-ng "1.4-1"
echo
echo "--- Without --allowerasing (expected: FAIL) ---"
echo "CMD: $DNF install foo-1.1-1.noarch --repo='poc-*'"
if dnf_cmd install -y --repo='poc-*' foo-1.1-1.noarch; then
    fail "S8 install foo-1.1 without --allowerasing succeeded (unexpected)"
else
    pass "S8 install foo-1.1 blocked without --allowerasing (as expected)"
fi
echo
echo "--- With --allowerasing (expected: PASS) ---"
echo "CMD: $DNF install --allowerasing foo-1.1-1.noarch --repo='poc-*'"
if dnf_cmd install -y --allowerasing --repo='poc-*' foo-1.1-1.noarch; then
    assert_ver    "S8 foo installed" foo "1.1-1"
    assert_origin "S8 foo origin"   foo "poc-artifact-test"
    # foo-ng should be gone (removed by --allowerasing)
    if ! rpm -q foo-ng &>/dev/null; then
        pass "S8 foo-ng removed by --allowerasing"
    else
        fail "S8 foo-ng still present after --allowerasing"
    fi
else
    fail "S8 install foo-1.1 with --allowerasing failed"
fi
remove_pkgs foo foo-ng
clear_artifact

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF5: Scenario 9 — Two-command pattern combined (install + reinstall)"
# Verifies the full proposed pattern from vaibhav_design.md:
#   Cmd 1: dnf install [--allow-downgrade] [--allowerasing] <nvra>
#   Cmd 2: dnf reinstall <pkg-name>
# Sub-cases: (a) newer installed, (b) same NVRA unknown origin

echo "=== 9a: Newer version installed (2.4 → 1.1 downgrade) ==="
remove_pkgs foo
install_direct foo-2.4-1
set_artifact foo-1.1-1
if [[ $DNF_VER -eq 5 ]]; then
    echo "CMD: $DNF install --allow-downgrade --allowerasing foo-1.1-1.noarch --repo='poc-*'"
    dnf_cmd install -y --allow-downgrade --allowerasing --repo='poc-*' foo-1.1-1.noarch
else
    echo "CMD: $DNF install --allowerasing foo-1.1-1.noarch --repo='poc-*'"
    dnf_cmd install -y --allowerasing --repo='poc-*' foo-1.1-1.noarch
fi
assert_ver    "S9a after install" foo "1.1-1"
assert_origin "S9a after install origin" foo "poc-artifact-test"
echo "CMD: $DNF reinstall foo --repo='poc-*'  (should be no-op, already correct origin)"
dnf_reinstall foo
assert_ver    "S9a after reinstall" foo "1.1-1"
assert_origin "S9a after reinstall origin" foo "poc-artifact-test"
remove_pkgs foo

echo
echo "=== 9b: Same NVRA, unknown origin (rpm -i) → reinstall fixes it ==="
# clear_artifact before install_direct: DNF5 resolves %{from_repo} dynamically, so
# any active artifact repo would make the "unknown origin" check a false pass.
clear_artifact
install_direct foo-1.1-1
echo "=== Before: from_repo=$(from_repo foo) (should be unknown) ==="
assert_not_origin "S9b origin before repo config" foo "poc-artifact-test"
set_artifact foo-1.1-1
if [[ $DNF_VER -eq 5 ]]; then
    dnf_cmd install -y --allow-downgrade --allowerasing --repo='poc-*' foo-1.1-1.noarch
else
    dnf_cmd install -y --allowerasing --repo='poc-*' foo-1.1-1.noarch
fi
echo "=== After install cmd: from_repo=$(from_repo foo) ==="
# DNF5: from_repo is dynamic — once artifact repo is configured it resolves immediately,
# so "install is no-op for origin" cannot be verified after set_artifact on DNF5.
if [[ $DNF_VER -ne 5 ]]; then
    assert_not_origin "S9b install is no-op for origin" foo "poc-artifact-test"
fi
dnf_reinstall foo
echo "=== After reinstall cmd: from_repo=$(from_repo foo) (expected: poc-artifact-test) ==="
assert_origin "S9b reinstall fixes origin" foo "poc-artifact-test"
assert_ver    "S9b version unchanged"      foo "1.1-1"
remove_pkgs foo
clear_artifact

# ── ─────────────────────────────────────────────────────────────────────────

header "DNF4-only: --allow-downgrade flag existence check"
if [[ $DNF_VER -eq 4 ]]; then
    echo "CMD: $DNF install --allow-downgrade (should FAIL — flag does not exist in DNF4)"
    if $DNF install --help 2>&1 | grep -q 'allow-downgrade'; then
        fail "DNF4 --allow-downgrade flag found (unexpected)"
    else
        pass "DNF4 --allow-downgrade flag does NOT exist (as expected)"
    fi
else
    skip "--allow-downgrade absence check (only relevant on DNF4)"
fi

# ── ─────────────────────────────────────────────────────────────────────────

header "Summary"
echo
echo -e "  ${GREEN}PASS: $PASS_COUNT${NC}"
echo -e "  ${RED}FAIL: $FAIL_COUNT${NC}"
echo -e "  ${YELLOW}SKIP: $SKIP_COUNT${NC}"
echo
if [[ $FAIL_COUNT -gt 0 ]]; then
    echo -e "${RED}Some scenarios failed — see above.${NC}"
    exit 1
else
    echo -e "${GREEN}All scenarios passed.${NC}"
fi
