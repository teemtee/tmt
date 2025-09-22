#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

SCRIPTS="
rhts-abort
rhts-reboot
rhts-report-result
rhts-submit-log
rhts_submit_log
rstrnt-abort
rstrnt-reboot
rstrnt-report-log
rstrnt-report-result
tmt-abort
tmt-file-submit
tmt-reboot
tmt-reboot-core
tmt-report-result
"

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "export LANG=C" 0 "Enforce standard error messages"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test script installation"
        # Run tmt with local provision
        rlRun -s "tmt --feeling-safe run --id $run -vvv"
        rlAssertNotGrep "No such file or directory" $rlRun_LOG
        rlAssertNotGrep "command not found" $rlRun_LOG
        rlAssertGrep "pass /test/beakerlib" $rlRun_LOG
        rlAssertGrep "pass /direct/good" $rlRun_LOG
        rlAssertGrep "skip /direct/skip" $rlRun_LOG

        # Check if the script was copied and is executable
        for script in $SCRIPTS; do
            script_path="$run/scripts/$script"
            rlAssertExists "$script_path"
            rlRun "test -x $script_path" 0 "Check if script is executable"
        done

        # Check that warning is raised when TMT_SCRIPTS_DIR is used
        rlRun -s "TMT_SCRIPTS_DIR=$tmp tmt --feeling-safe run --scratch --id $run -vvv"
        rlAssertGrep "The 'TMT_SCRIPTS_DIR' variable is not supported" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
