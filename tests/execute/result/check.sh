#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "pushd check"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check Results"
        rlRun -s "tmt run -a --id \${run} --scratch tests provision --how $PROVISION_HOW report -v 2>&1 >/dev/null | grep report -A19" "1"

        rlAssertGrep "pass /test/check-fail-info" "$rlRun_LOG"
        rlAssertGrep "fail /test/check-fail-respect (check 'dmesg' failed, original result: pass)" "$rlRun_LOG"
        rlAssertGrep "pass /test/check-override" "$rlRun_LOG"
        rlAssertGrep "pass /test/check-pass" "$rlRun_LOG"
        rlAssertGrep "pass /test/check-xfail-fail" "$rlRun_LOG"
        rlAssertGrep "fail /test/check-xfail-pass (check 'dmesg' failed, original result: pass)" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
