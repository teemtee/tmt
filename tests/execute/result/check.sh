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
        rlRun "tmt run -av --id $run provision --how $PROVISION_HOW" 1
        rlRun -s "tmt run --id $run report -v" 1

        rlAssertGrep "pass /test/check-fail-info (check 'dmesg' is informational)" "$rlRun_LOG"
        rlAssertGrep "fail /test/check-fail-respect (check 'dmesg' failed, original test result: pass)" "$rlRun_LOG"
        rlAssertGrep "pass /test/check-override (check 'dmesg' failed, test result overridden: pass)" "$rlRun_LOG"
        rlAssertGrep "pass /test/check-pass" "$rlRun_LOG"
        rlAssertGrep "fail /test/check-pass-test-xfail (test was expected to fail, original test result: pass)" "$rlRun_LOG"
        rlAssertGrep "pass /test/check-xfail-fail (check 'dmesg' failed as expected)" "$rlRun_LOG"
        rlAssertGrep "fail /test/check-xfail-pass (check 'dmesg' did not fail as expected, original test result: pass)" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
