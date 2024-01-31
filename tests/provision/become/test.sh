#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

PROVISION_METHODS=${PROVISION_METHODS:-container virtual}

rlJournalStart

    rlPhaseStartSetup
        rlRun "pushd data"
        if [[ "$PROVISION_METHODS" =~ "container" ]]; then
            # Try several times to build the container
            # https://github.com/teemtee/tmt/issues/2063
            build="podman build -t become-container-test:latest ."
            rlRun "rlWaitForCmd '$build' -m 5 -d 5" || rlDie "Unable to prepare the image"
        fi
    rlPhaseEnd

    for method in ${PROVISION_METHODS}; do
        if [ "$method" = "container" ] || [ "$method" = "virtual" ]; then
            rlPhaseStartTest "$method, test with become=true"
                rlRun "tmt --context provisiontest=$method run -rvvv plan --name /test/root"
            rlPhaseEnd

            rlPhaseStartTest "$method, test with become=false"
                rlRun "tmt --context provisiontest=$method run -rvvv plan --name /test/user"
            rlPhaseEnd

            rlPhaseStartTest "$method, prepare/finish inline with become=true"
                rlRun "tmt --context provisiontest=$method run -rvvv plan --name /prepare-finish/root/inline"
            rlPhaseEnd

            rlPhaseStartTest "$method, prepare/finish inline with become=false"
                rlRun "tmt --context provisiontest=$method run -rvvv plan --name /prepare-finish/user/inline"
            rlPhaseEnd

            rlPhaseStartTest "$method, prepare/finish scripts with become=true"
                rlRun "tmt --context provisiontest=$method run -rvvv plan --name /prepare-finish/root/scripts"
            rlPhaseEnd

            rlPhaseStartTest "$method, prepare/finish scripts with become=false"
                rlRun "tmt --context provisiontest=$method run -rvvv plan --name /prepare-finish/user/scripts"
            rlPhaseEnd
        fi
    done

    rlPhaseStartCleanup
        rlRun "popd"
        if [[ "$PROVISION_METHODS" =~ "container" ]]; then
            rlRun "podman image rm -f localhost/become-container-test:latest" 0 "Remove custom image"
        fi
    rlPhaseEnd
rlJournalEnd
