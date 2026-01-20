#!/bin/bash
# T-01: Login -t (test mode)
# Expected: Login after each test, NOT in finish

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

        # Create multiple tests
        mkdir -p tests
        for i in 1 2 3; do
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
    rlPhaseEnd

    rlPhaseStartTest "Test mode login -t"
        rlRun -s "tmt run -ar provision -h container login -t -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"

        # Should have 3 logins (one per test) in execute
        login_count=$(grep -c "interactive" "$rlRun_LOG")
        rlAssertEquals "Should have 3 logins" "$login_count" "3"

        # Verify logins are in execute step, not finish
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep -c interactive" 0 "Logins in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
