#!/bin/bash
# R-03: Result type - error
# Demonstrates error result type behavior (infrastructure issue)

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

        cat > tests/error1.fmf << 'EOF'
test: exit 99
EOF
        cat > tests/error1.sh << 'EOF'
exit 99
EOF
        chmod +x tests/error1.sh

        cat > tests/error2.fmf << 'EOF'
test: exit 99
EOF
        cat > tests/error2.sh << 'EOF'
exit 99
EOF
        chmod +x tests/error2.sh
    rlPhaseEnd

    rlPhaseStartTest "Result type - error"
        rlRun -s "tmt run -ar provision -h container login --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
