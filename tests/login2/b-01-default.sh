#!/bin/bash
# B-01: Default login (no options)
# Expected: Login at end of finish step

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init -t mini"

        # Remove the default example plan
        rm -f plans/example.fmf

        # Create a simple plan with tests
        cat > plan.fmf << 'EOF'
execute:
    how: tmt
discover:
    how: fmf
provision:
    how: container
EOF

        # Create test directory
        mkdir -p tests
        cat > tests/test.fmf << 'EOF'
test: echo "test1"; true
EOF
        cat > tests/test.sh << 'EOF'
#!/bin/bash
echo "test1"
true
EOF
        chmod +x tests/test.sh
    rlPhaseEnd

    rlPhaseStartTest "Default login"
        rlRun -s "tmt run -ar provision -h container login -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    finish$' -A5 '$rlRun_LOG' | grep -i interactive" 0 "Login in finish step"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
