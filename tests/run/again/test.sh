#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        # Run until report, always show guest (should use relative paths)
        rlRun "tmt run --id $run --until report report --how html --display-guest always"
        rlAssertGrep "guest.*worker" $run/plan/report/default-0/index.html
        rlAssertNotGrep "href.*$run" $run/plan/report/default-0/index.html

        # Run report again, use absolute paths (but still show guest)
        rlRun "tmt run --last report --again --how html --absolute-paths"
        rlAssertGrep "guest.*worker" $run/plan/report/default-0/index.html
        rlAssertGrep "href.*$run" $run/plan/report/default-0/index.html
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
