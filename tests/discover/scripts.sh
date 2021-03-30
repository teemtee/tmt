#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'set -o pipefail'
        rlRun 'pushd data'
    rlPhaseEnd

    plan='plan --name /smoke'

    rlPhaseStartTest 'Discover only'
        rlRun "tmt run discover $plan | tee output"
        rlAssertGrep '1 test discovered' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Selected steps'
        rlRun "tmt run discover provision execute $plan | tee output"
        rlAssertGrep '1 test discovered' 'output'
        rlAssertGrep 'discover' 'output'
        rlAssertGrep 'provision' 'output'
        rlAssertGrep 'execute' 'output'
        rlAssertNotGrep 'prepare' 'output'
        rlAssertNotGrep 'report' 'output'
        rlAssertNotGrep 'finish' 'output'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'popd'
        rlRun 'rm -f output' 0 'Removing tmp file'
    rlPhaseEnd
rlJournalEnd
