#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

# Make it easier to see what went wrong
export TMT_SHOW_TRACEBACK=1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Basic archive tests"
        plan="/plans/fmf/archive-url"
        rlRun -s "tmt run -i $run discover plans -n $plan"
        rlAssertGrep "2 tests selected" $rlRun_LOG
        plan_path="$run$plan"
        step_workdir="$plan_path/discover/default-0"
        rlAssertExists "$step_workdir/tests-main.tar.gz" 0 "Check that the archive is present"
        rlAssertExists "$step_workdir/tests/tests-main" 0 "Check that the extracted archive is present"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
