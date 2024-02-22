#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        if [[ "$PROVISION_HOW" == "container" ]]; then
            # Try several times to build the container
            # https://github.com/teemtee/tmt/issues/2063
            build="podman build -t become-container-test:latest ."
            rlRun "rlWaitForCmd '$build' -m 5 -d 5" || rlDie "Unable to prepare the image"
        fi
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, test with become=true"
        rlRun "tmt --context provisiontest=$PROVISION_HOW run -rvvv plan --name /test/root"
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, test with become=false"
        rlRun "tmt --context provisiontest=$PROVISION_HOW run -rvvv plan --name /test/user"
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, prepare/finish inline with become=true"
        rlRun "tmt --context provisiontest=$PROVISION_HOW run -rvvv plan --name /prepare-finish/root/inline"
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, prepare/finish inline with become=false"
        rlRun "tmt --context provisiontest=$PROVISION_HOW run -rvvv plan --name /prepare-finish/user/inline"
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, prepare/finish scripts with become=true"
        rlRun "tmt --context provisiontest=$PROVISION_HOW run -rvvv plan --name /prepare-finish/root/scripts"
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, prepare/finish scripts with become=false"
        rlRun "tmt --context provisiontest=$PROVISION_HOW run -rvvv plan --name /prepare-finish/user/scripts"
    rlPhaseEnd

    if [[ "$PROVISION_HOW" == "virtual" ]]; then
        rlPhaseStartTest "$PROVISION_HOW, umask with become=true"
            rlRun "tmt --context provisiontest=$PROVISION_HOW run -rvvv plan --name /umask"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"
        if [[ "$PROVISION_HOW" == "container" ]]; then
            rlRun "podman image rm -f localhost/become-container-test:latest" 0 "Remove custom image"
        fi
    rlPhaseEnd
rlJournalEnd
