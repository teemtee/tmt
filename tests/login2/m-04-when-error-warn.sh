#!/bin/bash
# M-04: Login --when error --when warn
# Expected: Login in finish if any errored OR warned

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
        cat > tests/error.fmf << 'EOF'
test: exit 99
EOF
        cat > tests/error.sh << 'EOF'
exit 99
EOF
        chmod +x tests/error.sh

        cat > tests/warn.fmf << 'EOF'
test: echo "warn: warning"; true
EOF
        cat > tests/warn.sh << 'EOF'
echo "warn: Warning message" >&2
true
EOF
        chmod +x tests/warn.sh
    rlPhaseEnd

    rlPhaseStartTest "Login --when error --when warn"
        rlRun -s "tmt run -ar provision -h container login --when error --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
