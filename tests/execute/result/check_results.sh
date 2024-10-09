#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test with passing checks"
        rlRun -s "tmt run -vvv test --name /test/check-pass"
        rlAssertGrep "pass /test/check-pass" $rlRun_LOG
        rlAssertGrep "pass dmesg" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with failing dmesg check (respect)"
        rlRun -s "tmt run -vvv test --name /test/check-fail-respect" 2
        rlAssertGrep "fail /test/check-fail-respect" $rlRun_LOG
        rlAssertGrep "fail dmesg" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with failing dmesg check (info)"
        rlRun -s "tmt run -vvv test --name /test/check-fail-info"
        rlAssertGrep "pass /test/check-fail-info" $rlRun_LOG
        rlAssertGrep "skip dmesg" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with passing dmesg check (xfail)"
        rlRun -s "tmt run -vvv test --name /test/check-xfail-pass" 2
        rlAssertGrep "fail /test/check-xfail-pass" $rlRun_LOG
        rlAssertGrep "pass dmesg" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with failing dmesg check (xfail)"
        rlRun -s "tmt run -vvv test --name /test/check-xfail-fail"
        rlAssertGrep "pass /test/check-xfail-fail" $rlRun_LOG
        rlAssertGrep "fail dmesg" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with multiple checks with different result interpretations"
        rlRun -s "tmt run -vvv test --name /test/check-multiple" 2
        rlAssertGrep "fail /test/check-multiple" $rlRun_LOG
        rlAssertGrep "fail dmesg" $rlRun_LOG
        rlAssertGrep "pass dmesg" $rlRun_LOG
        rlAssertGrep "info dmesg" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with failing dmesg check but overridden by test result"
        rlRun -s "tmt run -vvv test --name /test/check-override"
        rlAssertGrep "pass /test/check-override" $rlRun_LOG
        rlAssertGrep "fail dmesg" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
