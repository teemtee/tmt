#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        # Go into the directory with the plan
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test data is pulled after finish"
        # Run the plan up to the 'finish' step, but stop before 'cleanup'
        rlRun "tmt run --until finish plans -n /plan"

        # After the run is finished, log in and check if the file
        # created in the 'finish' step was pulled to the host.
        # We tee the output to a file because the interactive login
        # output might not be captured by rlRun's default log.
        rlRun "tmt run --last login --command 'cat \$TMT_PLAN_DATA/message' | tee output.log"
        rlAssertGrep "hi" "output.log"
    rlPhaseEnd

    rlPhaseStartCleanup
        # Clean up the run now that the test is complete
        rlRun "tmt run --last finish"
        rlRun "rm -f output.log"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
