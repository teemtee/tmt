#!/bin/bash
# T-02: Login -t --when fail
# Expected: Login only after failed tests, NOT in finish

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init -t mini"
        # Remove the default example plan
        rm -f plans/example.fmf

        # Create a simple plan with tests
        cat > plan.fmf << 'EOF'
execute:
    how: tmt
discover:
    how: fmf
provision:
    how: container
EOF

        # Create tests with mixed results
        mkdir -p tests
        cat > tests/pass.fmf << 'EOF'
test: echo "pass"; true
EOF
        cat > tests/pass.sh << 'EOF'
#!/bin/bash
echo "pass"
true
EOF
        chmod +x tests/pass.sh

        cat > tests/fail.fmf << 'EOF'
test: echo "fail"; false
EOF
        cat > tests/fail.sh << 'EOF'
#!/bin/bash
echo "fail"
false
EOF
        chmod +x tests/fail.sh
    rlPhaseEnd

    rlPhaseStartTest "Test mode with -t --when fail"
        rlRun -s "tmt run -ar provision -h container login -t --when fail -c true"

        # Should have 1 login (only after failed test)
        login_count=$(grep -c "interactive" "$rlRun_LOG")
        rlAssertEquals "Should have 1 login" "$login_count" "1"

        # Verify login happened in execute, not finish
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep interactive" 0 "Login in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
