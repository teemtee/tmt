#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

# TODO Sync the list with TEST_VIRTUAL_IMAGES in tests/images.sh.
# For now we cover just generic names without version numbers.

# TODO Include 'rocky' and 'oracle' as well once they are fixed:
# https://github.com/teemtee/tmt/issues/4239

IMAGES="fedora centos-stream ubuntu debian alma"

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    for image in $IMAGES; do
        rlPhaseStartTest "Test the $image image"
            rlRun "tmt run --all --id $run --scratch \
                provision --how virtual --image $image"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
