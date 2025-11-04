#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"

        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        build_container_image "fedora/latest\:latest"
        # TODO: Move this back to latest after avc issue is resolved
        # build_container_image "fedora/latest/bootc\:latest"
        build_container_image "fedora/42/bootc\:latest"
    rlPhaseEnd

    rlPhaseStartTest
        # List of paths to check, on a single line
        PATHS=$(echo $FOUND $NOT_FOUND)

        rlRun -s "tmt run -vvv -e \"PATHS='$PATHS'\" --id $run -a provision -h $PROVISION_HOW --image $IMAGE" 0 "Run the plan"

        for FOUND_PATH in $FOUND; do
            rlAssertGrep "out: $FOUND_PATH" $rlRun_LOG
        done

        for NOT_FOUND_PATH in $NOT_FOUND; do
            rlAssertGrep "ls: cannot access '$NOT_FOUND_PATH': No such file or directory" $rlRun_LOG
        done

        TMT_SCRIPTS_DIR=${TMT_SCRIPTS_DIR:-$DEFAULT_TMT_SCRIPTS_DIR}
        rlAssertGrep "PATH=.*$TMT_SCRIPTS_DIR.*" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
