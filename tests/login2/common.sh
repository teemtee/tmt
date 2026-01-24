#!/bin/bash
# Common functions for login2 test suite
#
# === Test Suite Context ===
# This test suite validates the fix for GitHub Issue #1918:
#
# THE BUG:
#   When using `tmt login -t` (test mode), the command incorrectly triggers
#   login in BOTH the execute step (after each test) AND the finish step (at the end).
#
#   This is unintended because:
#   - The `-t` flag is specifically designed for per-test login during execute step
#   - Users expect `login -t` to only log in after each test, not again at finish
#   - This duplicate login is confusing and wastes time
#
# ROOT CAUSE:
#   In `tmt/steps/__init__.py`, the `Login._parse_phases()` method:
#   - When no `--step` is provided, it defaults to the last enabled step (typically `finish`)
#   - The `-t` flag sets `Login._enabled = True` for per-test behavior
#   - But it doesn't prevent the default step (finish) from also triggering login
#
# THE FIX (PR #1933):
#   When `-t` is used without explicit `--step`, implicitly add `--step execute`
#   to ensure that:
#   - `login -t` only logs in during execute step (per-test)
#   - `login -t --when fail` only logs in after failing tests (in execute)
#   - No duplicate login in finish step
#
# ADDITIVE BEHAVIOR: Explicit `--step` combines with `-t`:
#   - `login -t --step finish` → login per-test (execute) AND also at finish
#   - `login -t --when fail --step finish` → login after failing tests (execute) AND at finish if any failed
#
# === Test Categories ===
#   B-01 to B-15: Base scenarios (default behavior without -t flag)
#   T-01 to T-12: Test mode scenarios (per-test login with -t flag)
#   C-01 to C-10: Combined scenarios (multiple option combinations)
#   M-01 to M-08: Multiple conditions (multiple --when clauses)
#   E-01 to E-12: Edge cases (boundary conditions)
#   R-01 to R-05: Result variations (different result types)
#
# === Key Behavioral Rules ===
#
# 1. Step Hierarchy:
#    - Without `--step`, login defaults to the last enabled step (typically `finish`)
#    - With `--step`, login occurs at the specified step
#
# 2. Test Mode (-t):
#    - `-t` means "per-test" during execute step
#    - Without explicit `--step execute`, `-t` should implicitly add `--step execute`
#    - `-t` with explicit `--step finish` is ADDITIVE: logs per-test AND at finish
#
# 3. When Conditions:
#    - `--when RESULT` filters when login should occur based on test results
#    - Multiple `--when` conditions are OR'd together (login if ANY condition matches)
#    - With `-t`, conditions are evaluated per-test
#    - Without `-t`, conditions are evaluated at the end (finish step)
#
# 4. Step Availability:
#    - `discover`: No guests ready → Error
#    - `provision`: No guests ready → Error
#    - `prepare`: Guests available → Login works
#    - `execute`: Guests available → Login works (per-test with `-t`)
#    - `finish`: Guests available → Login works (default)
#    - `report`: Guests available → Login works
#
# 5. Multiple Steps:
#    - Multiple `--step` options are ADDITIVE
#    - `--step execute --step finish` means login in BOTH steps
#    - Order doesn't matter for different steps

# =============================================================================
# Setup and Cleanup Functions
# =============================================================================

# Setup: Create temporary directory and initialize tmt project
# Creates a clean temporary workspace, initializes a mini tmt project,
# and removes the default example plan that comes with tmt init.
login2_setup() {
    rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
    rlRun "pushd $tmp"
    rlRun "set -o pipefail"
    rlRun "tmt init -t mini"
    rm -f plans/example.fmf
}

# Cleanup: Remove temporary directory
# Cleans up the temporary workspace after tests complete.
login2_cleanup() {
    rlRun "popd"
    rlRun "rm -r $tmp" 0 "Removing tmp directory"
}

# =============================================================================
# Plan Creation Functions
# =============================================================================

# Create standard plan.fmf
# Usage: login2_create_plan [with_prepare]
#
# Args:
#   with_prepare (optional): Set to "true" to include prepare step
#
# Creates a standard tmt plan with container provisioner. Most tests
# use this basic plan configuration.
login2_create_plan() {
    local with_prepare=${1:-false}
    if [ "$with_prepare" = "true" ]; then
        cat > plan.fmf << 'EOF'
execute:
    how: tmt
discover:
    how: fmf
provision:
    how: container
prepare:
    - how: shell
      script: echo "Preparing..."
EOF
    else
        cat > plan.fmf << 'EOF'
execute:
    how: tmt
discover:
    how: fmf
provision:
    how: container
EOF
    fi
}

# Create custom plan.fmf with additional content (via stdin or heredoc)
# Allows tests to provide custom plan configuration when needed.
login2_create_custom_plan() {
    cat > plan.fmf
}

# Create plan.fmf with no tests (for edge cases)
# Used in tests that verify behavior when no tests are discovered.
# The discover filter points to a non-existent path.
login2_create_plan_no_tests() {
    cat > plan.fmf << 'EOF'
execute:
    how: tmt
discover:
    how: fmf
    test:
    - "/nonexistent/path/*"
provision:
    how: container
EOF
}

# Create plan.fmf with report step (for report step tests)
# Used in tests that verify login behavior during the report step.
login2_create_plan_with_report() {
    cat > plan.fmf << 'EOF'
execute:
    how: tmt
discover:
    how: fmf
provision:
    how: container
report:
    how: display
EOF
}

# =============================================================================
# Single Test Creation Functions
# =============================================================================

# Create a single test
# Usage: login2_create_test <name> <command> [<fmf_content>]
#
# Args:
#   name: Test name (used for filename)
#   command: Shell command to execute
#   fmf_content (optional): Custom FMF content (defaults to "test: <command>")
#
# Creates both the .fmf metadata file and the executable .sh script.
login2_create_test() {
    local name=$1
    local command=$2
    local fmf_content=${3:-test: $command}

    mkdir -p tests
    cat > tests/$name.fmf << EOF
$fmf_content
EOF
    cat > tests/$name.sh << EOF
#!/bin/bash
$command
EOF
    chmod +x tests/$name.sh
}

# Create a passing test (exits with 0)
# Used as a baseline test that always succeeds.
login2_create_pass_test() {
    login2_create_test "pass" "true" "test: true"
}

# Create a failing test (exits with 1)
# Used to verify login behavior when tests fail.
login2_create_fail_test() {
    login2_create_test "fail" "false" "test: false"
}

# Create an error test (exits with 99)
# In tmt, exit code 99 represents an error (infrastructure issue),
# distinct from a test failure (exit code 1).
login2_create_error_test() {
    login2_create_test "error" "exit 99" "test: exit 99"
}

# Create a warning test (using stderr for simplicity)
# Outputs to stderr to trigger a warning result in tmt.
# The test still passes (exit 0) but produces a warning.
login2_create_warn_test() {
    mkdir -p tests
    cat > tests/warn.fmf << 'EOF'
test: echo "warn: warning"; true
EOF
    cat > tests/warn.sh << 'EOF'
echo "warn: This is a warning" >&2
true
EOF
    chmod +x tests/warn.sh
}

# Create a "normal" passing test (often used alongside error tests)
# Named "normal" to distinguish it from error/fail tests in scenarios
# that mix different result types.
login2_create_normal_test() {
    login2_create_test "normal" "true" "test: true"
}

# Create an info test
# Info results require beakerlib's rlLogInfo function.
# Used to verify login behavior with info-level results.
login2_create_info_test() {
    # Info result requires beakerlib
    login2_create_test "info" ". /usr/share/beakerlib/beakerlib.sh && rlLogInfo 'info'" "test: echo info; rlLogInfo"
}

# =============================================================================
# Multiple Test Creation Functions
# =============================================================================

# Create multiple passing tests
# Usage: login2_create_tests <count>
#
# Args:
#   count: Number of tests to create (test1, test2, etc.)
#
# Used to verify per-test login behavior with multiple tests.
login2_create_tests() {
    local count=$1
    mkdir -p tests
    for i in $(seq 1 $count); do
        cat > tests/test$i.fmf << EOF
test: echo "test$i"; true
EOF
        cat > tests/test$i.sh << EOF
#!/bin/bash
echo "test$i"
true
EOF
        chmod +x tests/test$i.sh
    done
}

# Create multiple fail tests (used in edge case tests)
# Usage: login2_create_fail_tests <count>
#
# Args:
#   count: Number of failing tests to create
#
# Used in tests that verify behavior when all tests fail.
login2_create_fail_tests() {
    local count=$1
    mkdir -p tests
    for i in $(seq 1 $count); do
        cat > tests/test$i.fmf << EOF
test: false
EOF
        cat > tests/test$i.sh << 'EOF'
false
EOF
        chmod +x tests/test$i.sh
    done
}

# =============================================================================
# Test Combination Functions
# These functions create specific combinations of test types
# =============================================================================

# Create pass1 and pass2 tests (used in when-pass tests)
# Used when tests need multiple passing tests with distinct names.
login2_create_two_pass_tests() {
    login2_create_test "pass1" "true"
    login2_create_test "pass2" "true"
}

# Create two fail tests (fail1, fail2)
# Used when tests need multiple failing tests with distinct names.
login2_create_two_fail_tests() {
    mkdir -p tests
    for i in 1 2; do
        cat > tests/fail$i.fmf << EOF
test: false
EOF
        cat > tests/fail$i.sh << 'EOF'
false
EOF
        chmod +x tests/fail$i.sh
    done
}

# Create two error tests (error1, error2)
# Used when tests need multiple error tests with distinct names.
login2_create_two_error_tests() {
    mkdir -p tests
    for i in 1 2; do
        cat > tests/error$i.fmf << EOF
test: exit 99
EOF
        cat > tests/error$i.sh << 'EOF'
exit 99
EOF
        chmod +x tests/error$i.sh
    done
}

# Create two warn tests (warn1, warn2) with stderr output
# Used to verify that login occurs when tests produce warnings.
login2_create_two_warn_tests() {
    mkdir -p tests
    cat > tests/warn1.fmf << 'EOF'
test: echo "warn: warning"; true
EOF
    cat > tests/warn1.sh << 'EOF'
echo "warn: Warning message" >&2
true
EOF
    chmod +x tests/warn1.sh

    cat > tests/warn2.fmf << 'EOF'
test: echo "warn: warning2"; true
EOF
    cat > tests/warn2.sh << 'EOF'
echo "warn: Another warning" >&2
true
EOF
    chmod +x tests/warn2.sh
}

# Create pass1+pass2+fail tests (used in multiple condition tests)
# Used to verify behavior with a mix of passing and failing tests.
login2_create_two_pass_and_fail_tests() {
    login2_create_test "pass1" "true"
    login2_create_fail_test
    login2_create_test "pass2" "true"
}

# Create pass+fail+error tests (used in multiple condition tests)
# Covers all three main result types (pass, fail, error).
login2_create_pass_fail_error_tests() {
    login2_create_pass_test
    login2_create_fail_test
    login2_create_error_test
}

# Create fail+warn tests (used in multiple condition tests)
# Tests login behavior with both failing and warning results.
login2_create_fail_warn_tests() {
    login2_create_fail_test
    login2_create_warn_test
}

# Create error+warn tests (used in multiple condition tests)
# Tests login behavior with both error and warning results.
login2_create_error_warn_tests() {
    login2_create_error_test
    login2_create_warn_test
}

# =============================================================================
# Assertion Helper Functions
# =============================================================================

# Assert login count
# Usage: login2_assert_login_count <expected_count>
#
# Args:
#   expected: Expected number of logins
#
# Counts occurrences of "interactive" in the test output to verify
# the expected number of login attempts occurred.
login2_assert_login_count() {
    local expected=$1
    login_count=$(grep -c "interactive" "$rlRun_LOG")
    rlAssertEquals "Should have $expected login(s)" "$login_count" "$expected"
}

# Assert login in specific step
# Usage: login2_assert_login_in_step <step_name>
#
# Args:
#   step: Step name (e.g., "finish", "execute", "prepare", "report")
#
# Verifies that login occurred within a specific tmt step by checking
# the step output for the "interactive" marker.
login2_assert_login_in_step() {
    local step=$1
    rlRun "grep '^    $step$' -A5 '$rlRun_LOG' | grep -i interactive" 0 "Login in $step step"
}
