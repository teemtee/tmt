#!/bin/bash
# E-05: Login -t --when pass (all tests pass)
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
        cat > tests/test1.fmf << 'EOF'
test: true
EOF
        cat > tests/test1.sh << 'EOF'
true
EOF
        chmod +x tests/test1.sh

        cat > tests/test2.fmf << 'EOF'
test: true
EOF
        cat > tests/test2.sh << 'EOF'
true
EOF
        chmod +x tests/test2.sh

        cat > tests/test3.fmf << 'EOF'
test: true
EOF
        cat > tests/test3.sh << 'EOF'
true
EOF
        chmod +x tests/test3.sh
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when pass (all pass)"
        rlRun -s "tmt run -ar provision -h container login -t --when pass -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login_count=$(grep -c "interactive" "$rlRun_LOG")
        rlAssertEquals "Should have 3 logins" "$login_count" "3"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
