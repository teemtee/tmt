#!/bin/bash
# R-02: Result type - fail
# Demonstrates fail result type behavior

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

        cat > tests/fail1.fmf << 'EOF'
test: false
EOF
        cat > tests/fail1.sh << 'EOF'
false
EOF
        chmod +x tests/fail1.sh

        cat > tests/fail2.fmf << 'EOF'
test: false
EOF
        cat > tests/fail2.sh << 'EOF'
false
EOF
        chmod +x tests/fail2.sh
    rlPhaseEnd

    rlPhaseStartTest "Result type - fail"
        rlRun -s "tmt run -ar provision -h container login --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
