#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "export TMT_SCRIPTS_DIR=$tmp"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test script installation"
        # Run tmt with local provision
        rlRun "tmt --feeling-safe run provision plan -n script"

        # Check if the script was installed in the default location
        script_path="$tmp/tmt-abort"
        rlAssertExists "$script_path"

        # Check if the script is executable
        rlRun "test -x $script_path" 0 "Check if script is executable"

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
