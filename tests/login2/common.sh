#!/bin/bash
# Common functions for login2 test suite

# Setup: Create temporary directory and initialize tmt project
login2_setup() {
    rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
    rlRun "pushd $tmp"
    rlRun "set -o pipefail"
    rlRun "tmt init -t mini"
    rm -f plans/example.fmf
}

# Cleanup: Remove temporary directory
login2_cleanup() {
    rlRun "popd"
    rlRun "rm -r $tmp" 0 "Removing tmp directory"
}

# Create standard plan.fmf
# Usage: login2_create_plan [with_prepare]
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
login2_create_custom_plan() {
    cat > plan.fmf
}

# Create plan.fmf with no tests (for edge cases)
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

# Create a single test
# Usage: login2_create_test <name> <command> [<fmf_content>]
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

# Create multiple passing tests
# Usage: login2_create_tests <count>
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

# Create a passing test
login2_create_pass_test() {
    login2_create_test "pass" "true" "test: true"
}

# Create a failing test
login2_create_fail_test() {
    login2_create_test "fail" "false" "test: false"
}

# Create an error test (exit 99)
login2_create_error_test() {
    login2_create_test "error" "exit 99" "test: exit 99"
}

# Create a warning test (using stderr for simplicity)
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
login2_create_normal_test() {
    login2_create_test "normal" "true" "test: true"
}

# Create pass1 and pass2 tests (used in when-pass tests)
login2_create_two_pass_tests() {
    login2_create_test "pass1" "true"
    login2_create_test "pass2" "true"
}

# Create an info test
login2_create_info_test() {
    # Info result requires beakerlib
    login2_create_test "info" ". /usr/share/beakerlib/beakerlib.sh && rlLogInfo 'info'" "test: echo info; rlLogInfo"
}

# Create two warn tests (warn1, warn2) with stderr output
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

# Create pass+fail+error tests (used in multiple condition tests)
login2_create_pass_fail_error_tests() {
    login2_create_pass_test
    login2_create_fail_test
    login2_create_error_test
}

# Create fail+warn tests (used in multiple condition tests)
login2_create_fail_warn_tests() {
    login2_create_fail_test
    login2_create_warn_test
}

# Create error+warn tests (used in multiple condition tests)
login2_create_error_warn_tests() {
    login2_create_error_test
    login2_create_warn_test
}

# Create pass1+pass2+fail tests (used in multiple condition tests)
login2_create_two_pass_and_fail_tests() {
    login2_create_test "pass1" "true"
    login2_create_fail_test
    login2_create_test "pass2" "true"
}

# Create multiple fail tests (used in edge case tests)
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

# Create two error tests (error1, error2)
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

# Create two fail tests (fail1, fail2)
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

# Create two pass tests (pass1, pass2)
login2_create_two_pass_tests() {
    mkdir -p tests
    for i in 1 2; do
        cat > tests/pass$i.fmf << EOF
test: true
EOF
        cat > tests/pass$i.sh << 'EOF'
true
EOF
        chmod +x tests/pass$i.sh
    done
}

# Assert login count
# Usage: login2_assert_login_count <expected_count>
login2_assert_login_count() {
    local expected=$1
    login_count=$(grep -c "interactive" "$rlRun_LOG")
    rlAssertEquals "Should have $expected login(s)" "$login_count" "$expected"
}

# Assert login in specific step
# Usage: login2_assert_login_in_step <step_name>
login2_assert_login_in_step() {
    local step=$1
    rlRun "grep '^    $step$' -A5 '$rlRun_LOG' | grep -i interactive" 0 "Login in $step step"
}
