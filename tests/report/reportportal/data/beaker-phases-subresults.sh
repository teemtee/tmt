#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1


rlJournalStart
    rlPhaseStartSetup "phase-setup"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
    rlPhaseEnd

    rlPhaseStartTest "phase-test pass"
        rlRun -s "echo mytest-pass" 0 "Check output"
        rlAssertGrep "mytest-pass" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "phase-test fail"
        rlRun -s "echo mytest-fail" 0 "Check output"
        rlAssertGrep "this-will-intentionally-fail" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "phase-test multiple tmt-report-result"
        rlRun "echo bkr_good_log > bkr_good.log"
        rlRun "echo bkr_bad_log > bkr_bad.log"
        rlRun "echo bkr_weird_log > bkr_weird.log"
        rlRun "echo bkr_skip_log > bkr_skip.log"
        rlRun "echo bkr_good_rhts_log > bkr_good_rhts.log"

        # This will create more subresults for each
        # tmt-report-result/rhts-report-result call
        rlRun "tmt-report-result -o bkr_good.log extra-tmt-report-result/good PASS"
        rlRun "tmt-report-result -o bkr_bad.log extra-tmt-report-result/bad FAIL"
        rlRun "tmt-report-result -o bkr_weird.log extra-tmt-report-result/weird WARN"
        rlRun "tmt-report-result -o bkr_skip.log extra-tmt-report-result/skip SKIP"
        rlRun "rhts-report-result extra-rhts-report-result/good PASS bkr_good_rhts.log"
    rlPhaseEnd

    rlPhaseStartCleanup "phase-cleanup"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
