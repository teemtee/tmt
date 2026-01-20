#!/bin/bash
# R-04: Result type - warn
# Demonstrates warn result type behavior

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

        cat > tests/warn1.fmf << 'EOF'
test: echo "warn: warning"; true
EOF
        cat > tests/warn1.sh << 'EOF'
echo "warn: This is a warning" >&2
true
EOF
        chmod +x tests/warn1.sh

        cat > tests/warn2.fmf << 'EOF'
test: echo "warn: warning2"; true
EOF
        cat > tests/warn2.sh << 'EOF'
echo "warn: Another warning" >&2
true
EOF
        chmod +x tests/warn2.sh
    rlPhaseEnd

    rlPhaseStartTest "Result type - warn"
        rlRun -s "tmt run -ar provision -h container login --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
