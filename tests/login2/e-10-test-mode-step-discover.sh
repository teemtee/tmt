#!/bin/bash
# E-10: Login -t --step discover (override)
# Expected: No guests ready in discover

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

    rlPhaseStartTest "Login -t --step discover (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step discover -c true" 0-2
        rlAssertGrep "No guests ready for login" "$rlRun_LOG" 0 "No guests in discover"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
