#!/bin/bash
# B-07: Login --step finish
# Expected: Login in finish step (explicit)

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
        cat > tests/test.fmf << 'EOF'
test: true
EOF
        cat > tests/test.sh << 'EOF'
true
EOF
        chmod +x tests/test.sh
    rlPhaseEnd

    rlPhaseStartTest "Login --step finish"
        rlRun -s "tmt run -ar provision -h container login --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    finish$' -A5 '$rlRun_LOG' | grep -i interactive" 0 "Login in finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
