#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test with passing checks"
        rlRun -s "tmt run -vvv test --name /test/check-pass" 0
        rlAssertGrep "pass dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "pass dmesg (after-test check)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with failing dmesg check (respect)"
        rlRun -s "tmt run -vvv test --name /test/check-fail-respect" 2
        rlAssertGrep "pass dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "fail dmesg (after-test check)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with failing dmesg check (info)"
        rlRun -s "tmt run -vvv test --name /test/check-fail-info" 0
        rlAssertGrep "info dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "info dmesg (after-test check)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with passing dmesg check (xfail)"
        rlRun -s "tmt run -vvv test --name /test/check-xfail-pass" 2
        rlAssertGrep "pass dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "fail dmesg (after-test check)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with failing dmesg check (xfail)"
        rlRun -s "tmt run -vvv test --name /test/check-xfail-fail" 0
        rlAssertGrep "pass dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "fail dmesg (after-test check)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with multiple checks with different result interpretations"
        rlRun -s "tmt run -vvv test --name /test/check-multiple" 2
        rlAssertGrep "pass dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "fail dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "pass dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "fail dmesg (after-test check)" $rlRun_LOG
        rlAssertGrep "info dmesg (after-test check)" $rlRun_LOG
        rlAssertGrep "info dmesg (after-test check)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test with failing dmesg check but overridden by test result"
        rlRun -s "tmt run -vvv test --name /test/check-override" 0
        rlAssertGrep "pass dmesg (before-test check)" $rlRun_LOG
        rlAssertGrep "fail dmesg (after-test check)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
