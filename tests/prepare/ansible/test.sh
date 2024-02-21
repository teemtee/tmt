#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
    rlPhaseEnd

    for plan in "local" "remote"; do
        rlPhaseStartTest "Test $plan playbook ($PROVISION_HOW)"
            rlRun "tmt run -arv provision -h $PROVISION_HOW plan -n /$plan"

            # For container provision try centos images as well
            if [[ $PROVISION_HOW == container ]]; then
                rlRun "tmt run -arv provision -h $PROVISION_HOW -i centos:7 plan -n /$plan"
                rlRun "tmt run -arv provision -h $PROVISION_HOW -i centos:stream8 plan -n /$plan"
            fi

            # After the local provision remove the test file
            if [[ $PROVISION_HOW == local ]]; then
                rlRun "sudo rm -f /tmp/prepared"
            fi
        rlPhaseEnd

        rlPhaseStartTest "Ansible ($PROVISION_HOW) - check extra-args attribute"
            rlRun "tmt run -rddd discover provision -h $PROVISION_HOW prepare finish plan -n /$plan 2>&1 >/dev/null \
                | grep \"ansible-playbook\"\
                | tee output"
            rlAssertGrep "-vvv" output
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
