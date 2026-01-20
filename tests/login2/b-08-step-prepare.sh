#!/bin/bash
# B-08: Login --step prepare
# Expected: Login in prepare step

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
prepare:
    - how: shell
      script: echo "Preparing..."
EOF

        mkdir -p tests
        cat > tests/test.fmf << 'EOF'
test: true
EOF
        cat > tests/test.sh << 'EOF'
true
EOF
        chmod +x tests/test.sh
    rlPhaseEnd

    rlPhaseStartTest "Login --step prepare"
        rlRun -s "tmt run -ar provision -h container login --step prepare -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    prepare$' -A20 '$rlRun_LOG' | grep -i interactive" 0 "Login in prepare"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
