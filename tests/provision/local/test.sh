#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "export TMT_SCRIPTS_DIR=/var/tmp/helper/scripts"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test script installation"
        # Run tmt with local provision
        rlRun "tmt --feeling-safe run provision plan -n script"

        # Check if the script was installed in the default location
        script_path="/var/tmp/helper/scripts/tmt-abort"
        rlAssertExists "$script_path"

        # Check if the script is executable
        rlRun "test -x $script_path" 0 "Check if script is executable"

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
