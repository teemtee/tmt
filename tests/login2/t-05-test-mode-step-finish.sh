#!/bin/bash
# T-05: Login -t --step finish
# Expected: Login in finish (user overrode -t default)

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init -t mini"
        # Remove the default example plan
        rm -f plans/example.fmf

        cat > plan.fmf << 'EOF'
execute:
    how: tmt
discover:
    how: fmf
provision:
    how: container
EOF

        mkdir -p tests
        for i in 1 2; do
            cat > tests/test$i.fmf << EOF
test: true
EOF
            cat > tests/test$i.sh << 'EOF'
true
EOF
            chmod +x tests/test$i.sh
        done
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step finish (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"

        # Should have only 1 login in finish, not per-test
        login_count=$(grep -c "interactive" "$rlRun_LOG")
        rlAssertEquals "Should have 1 login" "$login_count" "1"

        # Verify it's in finish
        rlRun "grep '^    finish$' -A5 '$rlRun_LOG' | grep -i interactive" 0 "Login in finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
