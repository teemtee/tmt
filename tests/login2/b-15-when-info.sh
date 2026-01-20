#!/bin/bash
# B-15: Login --when info
# Expected: Login in finish if any test has info result

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
        cat > tests/info.fmf << 'EOF'
test: echo "info: message"; true
EOF
        cat > tests/info.sh << 'EOF'
echo "info: This is an info message" >&2
true
EOF
        chmod +x tests/info.sh
    rlPhaseEnd

    rlPhaseStartTest "Login --when info"
        rlRun -s "tmt run -ar provision -h container login --when info -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
