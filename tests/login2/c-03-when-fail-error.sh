#!/bin/bash
# C-03: Login --when fail --when error
# Expected: Login in finish if any failed OR errored

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
        cat > tests/pass.fmf << 'EOF'
test: true
EOF
        cat > tests/pass.sh << 'EOF'
true
EOF
        chmod +x tests/pass.sh

        cat > tests/fail.fmf << 'EOF'
test: false
EOF
        cat > tests/fail.sh << 'EOF'
false
EOF
        chmod +x tests/fail.sh

        cat > tests/error.fmf << 'EOF'
test: exit 99
EOF
        cat > tests/error.sh << 'EOF'
exit 99
EOF
        chmod +x tests/error.sh
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --when error"
        rlRun -s "tmt run -ar provision -h container login --when fail --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    finish$' -A5 '$rlRun_LOG' | grep -i interactive" 0 "Login in finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
