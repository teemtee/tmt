#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

PROVISION_METHODS=${PROVISION_METHODS:-container}

rlJournalStart
    if [[ "$PROVISION_METHODS" =~ container ]]; then
        rlPhaseStartSetup
            rlRun "pushd data"
            # Try several times to build the container
            # https://github.com/teemtee/tmt/issues/2063
            build="podman build -t become-container-test:latest ."
            rlRun "rlWaitForCmd '$build' -m 5 -d 5" || rlDie "Unable to prepare the image"
        rlPhaseEnd

        rlPhaseStartTest "Container, test with become=true"
            rlRun "tmt run -rvvv plan --name /test/root"
        rlPhaseEnd

        rlPhaseStartTest "Container, test with become=false"
            rlRun "tmt run -rvvv plan --name /test/user"
        rlPhaseEnd

        rlPhaseStartTest "Container, prepare/finish inline with become=true"
            rlRun "tmt run -rvvv plan --name /prepare-finish/root/inline"
        rlPhaseEnd

        rlPhaseStartTest "Container, prepare/finish inline with become=false"
            rlRun "tmt run -rvvv plan --name /prepare-finish/user/inline"
        rlPhaseEnd

        rlPhaseStartTest "Container, prepare/finish scripts with become=true"
            rlRun "tmt run -rvvv plan --name /prepare-finish/root/scripts"
        rlPhaseEnd

        rlPhaseStartTest "Container, prepare/finish scripts with become=false"
            rlRun "tmt run -rvvv plan --name /prepare-finish/user/scripts"
        rlPhaseEnd

        rlPhaseStartCleanup
            rlRun "popd"
            rlRun "podman image rm -f localhost/become-container-test:latest" 0 "Remove custom image"
        rlPhaseEnd
    fi
rlJournalEnd
