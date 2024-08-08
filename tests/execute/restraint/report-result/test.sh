#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest Smoke
        rlRun -s "tmt run -vvv --remove" 1
        rlAssertGrep "pass /report" $rlRun_LOG

        # smoke rstrnt
        rlAssertGrep "pass /smoke/rstrnt-good" $rlRun_LOG
        rlAssertNotGrep "fail /smoke/rstrnt-good" $rlRun_LOG
        rlAssertGrep "fail /smoke/rstrnt-bad" $rlRun_LOG
        rlAssertNotGrep "pass /smoke/rstrnt-bad" $rlRun_LOG
        rlAssertGrep "skip /smoke/rstrnt-skip" $rlRun_LOG
        rlAssertNotGrep "pass /smoke/rstrnt-skip" $rlRun_LOG
        rlAssertGrep "warn /smoke/rstrnt-warn" $rlRun_LOG
        rlAssertNotGrep "pass /smoke/rstrnt-warn" $rlRun_LOG

        # smoke rhts
        rlAssertGrep "pass /smoke/rhts-good" $rlRun_LOG
        rlAssertNotGrep "fail /smoke/rhts-good" $rlRun_LOG
        rlAssertGrep "fail /smoke/rhts-bad" $rlRun_LOG
        rlAssertNotGrep "pass /smoke/rhts-bad" $rlRun_LOG
        rlAssertGrep "skip /smoke/rhts-skip" $rlRun_LOG
        rlAssertNotGrep "pass /smoke/rhts-skip" $rlRun_LOG
        rlAssertGrep "warn /smoke/rhts-warn" $rlRun_LOG
        rlAssertNotGrep "pass /smoke/rhts-warn" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest Multi
        # multi rstrnt
        rlAssertGrep "pass /multi_reports/rstrnt-good" $rlRun_LOG
        rlAssertGrep "fail /multi_reports/rstrnt-bad" $rlRun_LOG
        rlAssertGrep "pass /multi_reports/rstrnt-skip" $rlRun_LOG
        rlAssertGrep "warn /multi_reports/rstrnt-warn" $rlRun_LOG

        # multi rhts
        rlAssertGrep "pass /multi_reports/rhts-good" $rlRun_LOG
        rlAssertGrep "fail /multi_reports/rhts-bad" $rlRun_LOG
        rlAssertGrep "pass /multi_reports/rhts-skip" $rlRun_LOG
        rlAssertGrep "warn /multi_reports/rhts-warn" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest Separate
        # separate restraint
        rlAssertGrep "pass /separate/separate_rstrnt_fail/test/good" $rlRun_LOG
        rlAssertGrep "warn /separate/separate_rstrnt_fail/test/weird" $rlRun_LOG
        rlAssertGrep "fail /separate/separate_rstrnt_fail/test/bad" $rlRun_LOG
        rlAssertGrep "pass /separate/separate_rstrnt_pass/test/good_1" $rlRun_LOG
        rlAssertGrep "pass /separate/separate_rstrnt_pass/test/good_2" $rlRun_LOG
        rlAssertGrep "pass /separate/separate_rstrnt_pass/test/good_3" $rlRun_LOG
        rlAssertGrep "skip /separate/separate_rstrnt_skip/test/skip_1" $rlRun_LOG
        rlAssertGrep "skip /separate/separate_rstrnt_skip/test/skip_2" $rlRun_LOG
        rlAssertGrep "skip /separate/separate_rstrnt_skip/test/skip_3" $rlRun_LOG

        # separate rhts
        rlAssertGrep "pass /separate/separate_rhts_fail/test/good" $rlRun_LOG
        rlAssertGrep "warn /separate/separate_rhts_fail/test/weird" $rlRun_LOG
        rlAssertGrep "fail /separate/separate_rhts_fail/test/bad" $rlRun_LOG
        rlAssertGrep "pass /separate/separate_rhts_pass/test/good_1" $rlRun_LOG
        rlAssertGrep "pass /separate/separate_rhts_pass/test/good_2" $rlRun_LOG
        rlAssertGrep "pass /separate/separate_rhts_pass/test/good_3" $rlRun_LOG
        rlAssertGrep "skip /separate/separate_rhts_skip/test/skip_1" $rlRun_LOG
        rlAssertGrep "skip /separate/separate_rhts_skip/test/skip_2" $rlRun_LOG
        rlAssertGrep "skip /separate/separate_rhts_skip/test/skip_3" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest Output
        rlRun "grep -A1 'pass /output/separate/good-no-log'   $rlRun_LOG | grep output.txt"
        rlRun "grep -A1 'pass /output/separate/good-with-log' $rlRun_LOG | grep fine.txt"
        rlRun "grep -A1 'fail /output/separate/bad-no-log'    $rlRun_LOG | grep output.txt"
        rlRun "grep -A1 'fail /output/separate/bad-with-log'  $rlRun_LOG | grep wrong.txt"
        rlRun "grep -A1 'fail /output/single'                 $rlRun_LOG | grep output.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
