#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        if [[ "$PROVISION_HOW" == "container" ]]; then
            . ../../images.sh || exit 1

            build_container_image "fedora/rawhide/unprivileged\:latest"
        fi
        rlRun "pushd data"
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
    rlPhaseEnd
rlJournalEnd
