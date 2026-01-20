#!/bin/bash
# E-06: Login -t with no tests discovered
# Expected: No login (no tests = no logins)

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
    test:
    - "/nonexistent/path/*"
provision:
    how: container
EOF
    rlPhaseEnd

    rlPhaseStartTest "Login -t with no tests discovered"
        rlRun -s "tmt run -ar provision -h container login -t -c true" 0-2
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
