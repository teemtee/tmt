#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "pushd check"
        rlRun "set -o pipefail"
        # Write pattern for tests that need pre-existing dmesg content
        rlRun "echo 'Fail Test Check Pattern' | sudo tee /dev/kmsg"
    rlPhaseEnd

    rlPhaseStartTest "Check Results"
        rlRun -s "tmt run -a --id \${run} --scratch tests provision --how $PROVISION_HOW report -v 2>&1 >/dev/null | grep report -A19" "1"

        rlAssertGrep "$(cat <<-EOF
pass /test/check-fail-info
    info dmesg (before-test check)
    info dmesg (after-test check)
fail /test/check-fail-respect (Check 'dmesg' failed, original result: pass)
    pass dmesg (before-test check)
    fail dmesg (after-test check)
pass /test/check-override
    pass dmesg (before-test check)
    fail dmesg (after-test check)
pass /test/check-pass
    pass dmesg (before-test check)
    pass dmesg (after-test check)
pass /test/check-xfail-fail
    warn dmesg (before-test check)
    pass dmesg (after-test check)
fail /test/check-xfail-pass (Check 'dmesg' failed, original result: pass)
    warn dmesg (before-test check)
    fail dmesg (after-test check)
EOF
)" "$rlRun_LOG" -F
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
