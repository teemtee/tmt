#!/bin/bash
# E-03: Login --when fail --step prepare
# Expected: No login or error (--when with step before execute)

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
        cat > tests/fail.fmf << 'EOF'
test: false
EOF
        cat > tests/fail.sh << 'EOF'
false
EOF
        chmod +x tests/fail.sh
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --step prepare (edge case)"
        # This is an edge case - --when with a step before execute
        # The behavior is undefined/should be no login
        rlRun -s "tmt run -ar provision -h container login --when fail --step prepare -c true" 0-2
        # Document the actual behavior for now
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
