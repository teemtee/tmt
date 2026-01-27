#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
    rlPhaseEnd

    rlPhaseStartTest "Every test must have proper tag in junit report when test is marked as pending."
        rlRun -s "tmt run -vv -a -i $run provision -h $PROVISION_HOW report -h junit --file junit.xml " 2
        rlAssertGrep '<testsuite name="/plan" disabled="0" errors="1" failures="0" skipped="2" tests="4"' "junit.xml"
        rlAssertEquals "Check there is one error tag" $(grep '<error' 'junit.xml' | wc -l) 1
        rlAssertEquals "Check there are 2 skipped tags" $(grep '<skipped' 'junit.xml' | wc -l) 2
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
