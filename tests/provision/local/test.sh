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
        rlRun "tmp_root=\$(mktemp -d)"
        rlRun -s "tmt --feeling-safe run --workdir-root $tmp_root provision plan"

        # Check if the script was copied to the default location
        script_path="$tmp_root/run-001/scripts/tmt-file-submit"
        rlAssertExists "$script_path"

        # Check if the script is executable
        rlRun "test -x $script_path" 0 "Check if script is executable"

        # Check warning is raised
        rlAssertGrep "The TMT_SCRIPTS_DIR env is not supported" $rlRun_LOG

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $tmp_root" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
