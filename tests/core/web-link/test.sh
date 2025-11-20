#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "script='$PWD/test.py'"
        rlRun "tmp=\$(mktemp -d)" 0 "Create a tmp directory"
        rlRun "pushd $tmp"
        rlWaitForCmd "git clone https://github.com/teemtee/tests/" -m 5 -d 10 -t 300 || rlDie "Unable to clone tests repository"
        rlRun "pushd tests/tree"
        rlRun "cp '$script' ."
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "python3 -m pytest -vvv -ra --showlocals test.py"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd; popd"
        rlRun "rm -rf $tmp" 0 "Remove the tmp directory"
    rlPhaseEnd
rlJournalEnd
