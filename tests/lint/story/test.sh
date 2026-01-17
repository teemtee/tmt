#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Correct story"
        rlRun -s "tmt stories lint good" 0
        rlAssertGrep "pass C000 fmf node passes schema validation" $rlRun_LOG
        rlAssertGrep "pass S001 correct keys are used" $rlRun_LOG
        rlAssertNotGrep "warn" $rlRun_LOG
        rlAssertNotGrep "fail" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Incorrect story"
        rlRun -s "tmt stories lint long_summary" 0
        rlAssertGrep "warn C001 summary should not exceed 50 characters" $rlRun_LOG

        rlRun -s "tmt stories lint typo_in_key" 1
        rlAssertGrep "warn C000 fmf node failed schema validation" $rlRun_LOG
        rlAssertGrep "warn C001 summary key is missing" $rlRun_LOG
        rlAssertGrep "fail S001 unknown key \"exampleGG\" is used" $rlRun_LOG

        rlRun -s "tmt stories lint missing_story" 1
        rlAssertGrep "warn C000 fmf node failed schema validation" $rlRun_LOG
        rlAssertGrep "warn C001 summary key is missing" $rlRun_LOG
        rlAssertGrep "pass S001 correct keys are used" $rlRun_LOG
        rlAssertGrep "fail S002 story is required" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Lint of duplicate ids"
        # From data
        rlRun "popd"
        rlRun "pushd data_duplicate_ids"

        lint_cmd="tmt stories lint"

        rlRun -s "$lint_cmd /no_duplicates"
        rlAssertGrep "pass G001 no duplicate ids detected" "$rlRun_LOG"

        rlRun -s "$lint_cmd /duplicates" 1
        rlAssertGrep "fail G001 duplicate id \"5645dcdf-acaa-4a04-8c0d-d478c8a6f2a3\" in \"/duplicates/duplicate_one\"" "$rlRun_LOG"
        rlAssertGrep "fail G001 duplicate id \"5645dcdf-acaa-4a04-8c0d-d478c8a6f2a3\" in \"/duplicates/duplicate_two\"" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
