#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    # EPEL
    for method in ${PROVISION_METHODS:-"container"}; do
        rlPhaseStartTest "Enable and disable EPEL"
            rlRun -s "tmt run --all plan --name epel-enable provision --how $method"
            rlRun -s "tmt run --all plan --name epel-disable provision --how $method"

        rlPhaseEnd

        rlPhaseStartTest "Enable and disable EPEL with '--how feature' + '--epel'"
            rlRun -s "tmt run --all plan --name epel-disable provision " \
                     "--how $method prepare --how feature --epel enabled"
            rlRun -s "tmt run --all plan --name epel-enable provision " \
                     "--how $method prepare --how feature --epel disabled"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
