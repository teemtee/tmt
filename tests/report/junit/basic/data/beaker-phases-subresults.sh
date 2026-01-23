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
        rlAssertGrep "asdf-asdf" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "phase-test multiple tmt-report-result"
        # This will create more subresults for each tmt-report-result call
        rlRun "tmt-report-result extra-tmt-report-result/good PASS"
        rlRun "tmt-report-result extra-tmt-report-result/bad FAIL"
        rlRun "tmt-report-result extra-tmt-report-result/weird WARN"
        rlRun "tmt-report-result extra-tmt-report-result/skip SKIP"
    rlPhaseEnd

    rlPhaseStartCleanup "phase-cleanup"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
