#!/bin/bash
# R-05: Result type - info
# Demonstrates info result type behavior

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

        cat > tests/info1.fmf << 'EOF'
test: echo "info: message"; true
EOF
        cat > tests/info1.sh << 'EOF'
echo "info: This is an info message" >&2
true
EOF
        chmod +x tests/info1.sh

        cat > tests/info2.fmf << 'EOF'
test: echo "info: message2"; true
EOF
        cat > tests/info2.sh << 'EOF'
echo "info: More info" >&2
true
EOF
        chmod +x tests/info2.sh
    rlPhaseEnd

    rlPhaseStartTest "Result type - info"
        rlRun -s "tmt run -ar provision -h container login --when info -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
