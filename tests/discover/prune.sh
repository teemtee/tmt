#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd prune"
        rlRun "run=\$(mktemp -d)"
    rlPhaseEnd

    rlPhaseStartTest "Discover local"
        rlRun -s "tmt run -i $run discover plans --name plan tests --name test1"
        rlAssertExists "$run/plan/discover/default-0/tests/test1"
        rlAssertNotExists "$run/plan/discover/default-0/tests/test2"
        rlAssertNotExists "$run/plan/discover/default-0/tests/some-file"
    rlPhaseEnd

    rlPhaseStartTest "Discover remote with path"
        rlRun -s "tmt run -i $run discover plans --name nested tests --name file"
        rlAssertExists "$run/nested/discover/default-0/tests/file/test.sh"
        rlAssertExists "$run/nested/discover/default-0/tests/scripts/random_file.sh"
        rlAssertNotExists "$run/nested/discover/default-0/tests/dir-without-fmf"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
