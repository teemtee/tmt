#!/bin/bash
# R-01: Result type - pass
# Demonstrates pass result type behavior

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

        cat > tests/pass2.fmf << 'EOF'
test: true
EOF
        cat > tests/pass2.sh << 'EOF'
true
EOF
        chmod +x tests/pass2.sh

        cat > tests/fail.fmf << 'EOF'
test: false
EOF
        cat > tests/fail.sh << 'EOF'
false
EOF
        chmod +x tests/fail.sh
    rlPhaseEnd

    rlPhaseStartTest "Result type - pass"
        rlRun -s "tmt run -ar provision -h container login --when pass -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
