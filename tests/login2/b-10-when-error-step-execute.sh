#!/bin/bash
# B-10: Login --when error --step execute
# Expected: Login at end of execute if any test errored

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
        cat > tests/normal.fmf << 'EOF'
test: true
EOF
        cat > tests/normal.sh << 'EOF'
true
EOF
        chmod +x tests/normal.sh

        cat > tests/error.fmf << 'EOF'
test: exit 99
EOF
        cat > tests/error.sh << 'EOF'
exit 99
EOF
        chmod +x tests/error.sh
    rlPhaseEnd

    rlPhaseStartTest "Login --when error --step execute"
        rlRun -s "tmt run -ar provision -h container login --when error --step execute -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
