#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
    rlPhaseEnd

    rlPhaseStartTest "Every test must have proper tag in junit report when test is marked as pending."
        rlRun -s "tmt run -vv -a -i $run provision -h $PROVISION_HOW report -h junit --file junit.xml " 2
        rlAssertGrep '<testsuite name="/plan" disabled="0" errors="3" failures="0" skipped="0" tests="4"' "junit.xml"
        rlAssertEquals "Check there is one errored out test" $(grep '<error type="error" message="error"' 'junit.xml' | wc -l) 1
        rlAssertEquals "Check there are 2 errored out tests marked as pending" $(grep '<error type="error" message="pending"' 'junit.xml' | wc -l) 2
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
