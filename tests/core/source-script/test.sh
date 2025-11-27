#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
    rlPhaseEnd

    rlPhaseStartTest "Simple checks"
        # All tests are included in the tmt plan/test itself
        rlRun -s "tmt run --id $run -a provision --how=${PROVISION_HOW}" 0 "Run tests"
        # Make sure the file is still there
        rlAssertExists $run/plan/data/plan-source-script.sh
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
