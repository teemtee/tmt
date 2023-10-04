#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1


function assert_internal_fields () {
    log="$1"

    # Make sure internal fields are not exposed
    rlAssertNotGrep " _" $rlRun_LOG
    rlAssertNotGrep "serial-number" $log
    rlAssertNotGrep "data-path" $log
    rlAssertNotGrep "return-code" $log
    rlAssertNotGrep "start-time" $log
    rlAssertNotGrep "end-time" $log
    rlAssertNotGrep "real-duration" $log
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
        tnames="$(tmt tests ls)"
    rlPhaseEnd

    # 1 - (positive) format testing
    cmd="tmt tests export ."
    rlPhaseStartTest "$cmd"
        rlRun -s "$cmd | ../parse.py" 0 "Export test"
    rlPhaseEnd

    for tname in $tnames; do
        cmd="tmt tests export $tname"
        rlPhaseStartTest "$cmd"
            rlRun -s "$cmd" 0 "Export test"
            rlAssertGrep "name: $tname" $rlRun_LOG

            assert_internal_fields "$rlRun_LOG"
        rlPhaseEnd

        cmd="tmt tests export --how dict $tname"
        rlPhaseStartTest "$cmd"
            rlRun -s "$cmd" 0 "Export test"
            rlAssertGrep "'name': '$tname'" $rlRun_LOG
            rlAssertNotGrep "'_" $rlRun_LOG
            assert_internal_fields "$rlRun_LOG"
        rlPhaseEnd

        cmd="tmt tests export --how yaml $tname"
        rlPhaseStartTest "$cmd"
            rlRun -s "$cmd" 0 "Export test"
            rlAssertGrep "name: $tname" $rlRun_LOG
            assert_internal_fields "$rlRun_LOG"
        rlPhaseEnd
    done

    # 2 - (negative) format testing
    rlPhaseStartTest "Invalid format"
        rlRun -s "tmt tests export --how weird" 2
        if rlIsRHELLike "=8"; then
            # RHEL-8 and Centos stream 8 usually offer an older Click package that has slightly
            # different wording & quotes.
            rlAssertgrep "Error: Invalid value for \"-h\" / \"--how\": invalid choice: weird. (choose from dict, json, nitrate, polarion, yaml)" $rlRun_LOG
        else
            rlAssertGrep "Error: Invalid value for '-h' / '--how': 'weird' is not one of 'dict', 'json', 'nitrate', 'polarion', 'template', 'yaml'." $rlRun_LOG
        fi
    rlPhaseEnd

    # 3 - fmf-id testing
    cmd="tmt tests export . --fmf-id"
    rlPhaseStartTest "$cmd"
        rlRun -s "$cmd" 0 "Export test"
        for tname in $tnames; do
            rlAssertGrep "name: $tname" $rlRun_LOG
        done
    rlPhaseEnd

    for tname in $tnames; do
        cmd="tmt tests export --fmf-id $tname"
        rlPhaseStartTest "$cmd"
            rlRun -s "$cmd" 0 "Export test"
            rlAssertGrep "name: $tname" $rlRun_LOG
        rlPhaseEnd

        cmd="tmt tests export --how dict --fmf-id $tname"
        rlPhaseStartTest "$cmd"
            rlRun -s "$cmd" 0 "Export test"
            rlAssertGrep "'name': '$tname'" $rlRun_LOG
            rlAssertNotGrep "'_" $rlRun_LOG
        rlPhaseEnd

        cmd="tmt tests export --how yaml --fmf-id $tname"
        rlPhaseStartTest "$cmd"
            rlRun -s "$cmd" 0 "Export test"
            rlAssertGrep "name: $tname" $rlRun_LOG
            rlAssertNotGrep " _" $rlRun_LOG
        rlPhaseEnd
    done

    rlPhaseStartTest "Test does not exist"
        rlRun -s "tmt tests export --how yaml --fmf-id XXX" 0
        rlAssertGrep "\[\]" $rlRun_LOG

        rlRun -s "tmt tests export --how dict --fmf-id XXX" 0
        rlAssertGrep "\[\]" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
