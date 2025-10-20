#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        build_container_image "fedora/latest/unprivileged\:latest"

        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, default user root"
        rlRun -s "tmt run -i $run -a provision --how $PROVISION_HOW report -vvv"
        rlAssertGrep "uid=0(root) gid=0(root) groups=0(root)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, set specific user"
        image=""

        if [ "$PROVISION_HOW" = "container" ]; then
            image="--image $TEST_IMAGE_PREFIX/fedora/latest/unprivileged:latest"
        fi

        rlRun -s "tmt run --scratch -i $run -a provision --how $PROVISION_HOW $image --user fedora report -vvv"
        if [ "$PROVISION_HOW" = "container" ]; then
            rlAssertGrep "uid=1000(fedora) gid=1000(fedora) groups=1000(fedora)" $rlRun_LOG
        elif [ "$PROVISION_HOW" = "virtual" ]; then
            rlAssertGrep "uid=1000(fedora) gid=1001(fedora) groups=1001(fedora)" $rlRun_LOG
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
