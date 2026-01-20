#!/bin/bash
# M-02: Login --when fail --when warn
# Expected: Login in finish if any failed OR warned

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
        cat > tests/fail.fmf << 'EOF'
test: false
EOF
        cat > tests/fail.sh << 'EOF'
false
EOF
        chmod +x tests/fail.sh

        cat > tests/warn.fmf << 'EOF'
test: echo "warn: warning"; true
EOF
        cat > tests/warn.sh << 'EOF'
echo "warn: This is a warning" >&2
true
EOF
        chmod +x tests/warn.sh
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --when warn"
        rlRun -s "tmt run -ar provision -h container login --when fail --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
