#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test script installation"
        # Run tmt with local provision
        rlRun -s "tmt --feeling-safe run --id $run -vvv"

        # Check if the script was copied to the default location
        script_path="$run/scripts/tmt-file-submit"
        rlAssertExists "$script_path"

        # Check if the script is executable
        rlRun "test -x $script_path" 0 "Check if script is executable"

        # Check warning is raised
        rlRun -s "TMT_SCRIPTS_DIR=$tmp tmt --feeling-safe run --scratch --id $run provision"
        rlAssertGrep "The 'TMT_SCRIPTS_DIR' env is not supported" $rlRun_LOG

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
