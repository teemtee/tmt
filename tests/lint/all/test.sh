#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "All good"
        rlRun -s "tmt lint good" 0 "Lint correct metadata"
        rlAssertGrep "tests/good" $rlRun_LOG
        rlAssertGrep "plans/good" $rlRun_LOG
        rlAssertGrep "stories/good" $rlRun_LOG
        rlAssertNotGrep "tests/bad" $rlRun_LOG
        rlAssertNotGrep "plans/bad" $rlRun_LOG
        rlAssertNotGrep "stories/bad" $rlRun_LOG
    rlPhaseEnd

    # Check that exit code is correct if only one level is wrong
    for bad in tests plans stories; do
        rlPhaseStartTest "Only bad $bad"
            rlRun -s "tmt lint '($bad/bad|good)'" 1 "Lint wrong $bad"
        rlPhaseEnd
    done

    rlPhaseStartTest "All bad"
        rlRun -s "tmt lint bad" 1 "Lint wrong metadata"
        rlAssertNotGrep "tests/good" $rlRun_LOG
        rlAssertNotGrep "plans/good" $rlRun_LOG
        rlAssertNotGrep "stories/good" $rlRun_LOG
        rlAssertGrep "tests/bad" $rlRun_LOG
        rlAssertGrep "plans/bad" $rlRun_LOG
        rlAssertGrep "stories/bad" $rlRun_LOG
        # linting story
        rlAssertGrep "warn C000 key \"exampleee\" not recognized by schema /schemas/story" $rlRun_LOG
        rlAssertGrep "warn C001 summary should not exceed 50 characters" $rlRun_LOG
        rlAssertGrep "fail S001 unknown key \"exampleee\" is used" $rlRun_LOG
        rlAssertGrep "pass S002 story key is defined" $rlRun_LOG
        # linting test
        rlAssertGrep "warn C000 key \"summarrry\" not recognized by schema, and does not match \"^extra-\" pattern" $rlRun_LOG
        rlAssertGrep "warn C001 summary key is missing" $rlRun_LOG
        rlAssertGrep "fail T001 unknown key \"summarrry\" is used" $rlRun_LOG
        rlAssertGrep "pass T002 test script is defined" $rlRun_LOG
        rlAssertGrep "pass T003 directory path is absolute" $rlRun_LOG
        rlAssertGrep "pass T004 test path '.*/tests/lint/all/data/tests/bad' does exist" $rlRun_LOG
        rlAssertGrep "skip T005 legacy relevancy not detected" $rlRun_LOG
        rlAssertGrep "skip T006 legacy 'coverage' field not detected" $rlRun_LOG
        rlAssertGrep "skip T007 not a manual test" $rlRun_LOG
        rlAssertGrep "skip T008 not a manual test" $rlRun_LOG
        #linting plan
        rlAssertGrep "warn C000 key \"discovery\" not recognized by schema /schemas/plan" $rlRun_LOG
        rlAssertGrep "warn C000 key \"prepareahoj\" not recognized by schema /schemas/plan" $rlRun_LOG
        rlAssertGrep "pass C001 summary key is set and is reasonably long" $rlRun_LOG
        rlAssertGrep "fail P001 unknown key \"discovery\" is used" $rlRun_LOG
        rlAssertGrep "fail P001 unknown key \"prepareahoj\" is used" $rlRun_LOG
        rlAssertGrep "pass P002 execute step defined with \"how\"" $rlRun_LOG
        rlAssertGrep "pass P003 execute step methods are all known" $rlRun_LOG
        rlAssertGrep "skip P004 discover step is not defined" $rlRun_LOG
        rlAssertGrep "skip P005 no remote fmf ids defined" $rlRun_LOG
        rlAssertGrep "pass P006 phases have unique names" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check --fix for tests"
        rlRun -s "tmt lint --fix fix" 0 "Fix the test"
        rlAssertGrep 'relevancy converted into adjust' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check empty fmf file"
        rlRun -s "tmt lint empty" 0 "Empty file should be ok"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
rlJournalEnd
