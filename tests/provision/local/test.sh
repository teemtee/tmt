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
        rlRun -s "tmt --feeling-safe run provision plan"

        # Check if the script was installed in the default location
        script_path="$tmp/tmt-file-submit"
        rlAssertExists "$script_path"

        # Check if the script is executable
        rlRun "test -x $script_path" 0 "Check if script is executable"

        # Check that the error is not in the log
        rlAssertNotGrep "No such file or directory" $rlRun_LOG

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
