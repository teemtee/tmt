#!/bin/bash
# M-07: Login -t --when pass --when fail
# Expected: Login after every test in execute

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
        cat > tests/pass1.fmf << 'EOF'
test: true
EOF
        cat > tests/pass1.sh << 'EOF'
true
EOF
        chmod +x tests/pass1.sh

        cat > tests/fail.fmf << 'EOF'
test: false
EOF
        cat > tests/fail.sh << 'EOF'
false
EOF
        chmod +x tests/fail.sh

        cat > tests/pass2.fmf << 'EOF'
test: true
EOF
        cat > tests/pass2.sh << 'EOF'
true
EOF
        chmod +x tests/pass2.sh
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when pass --when fail"
        rlRun -s "tmt run -ar provision -h container login -t --when pass --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login_count=$(grep -c "interactive" "$rlRun_LOG")
        rlAssertEquals "Should have 3 logins (all tests pass or fail)" "$login_count" "3"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
