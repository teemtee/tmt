#!/bin/bash
# E-12: Login -t --when fail (all tests fail)
# Expected: Login after every test (all meet condition)

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init -t mini"
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
        for i in 1 2 3; do
            cat > tests/test$i.fmf << EOF
test: false
EOF
            cat > tests/test$i.sh << 'EOF'
false
EOF
            chmod +x tests/test$i.sh
        done
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail (all fail)"
        rlRun -s "tmt run -ar provision -h container login -t --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login_count=$(grep -c "interactive" "$rlRun_LOG")
        rlAssertEquals "Should have 3 logins" "$login_count" "3"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
