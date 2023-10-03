#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    for method in ${PROVISION_METHODS:-"virtual"}; do
        rlPhaseStartTest "Enable EPEL"
            rlRun -s "tmt run plan --name epel-enable provision --how $method prepare"
            rlAssertGrep 'Repo epel.*enabled' "$rlRun_LOG"

            rlRun -s "tmt run plan --name epel-disable provision " \
                     "--how $method prepare --how feature --epel enabled"
            rlAssertGrep 'Repo epel.*enabled' "$rlRun_LOG"
        rlPhaseEnd

        rlPhaseStartTest "Disable EPEL"
            rlRun -s "tmt run plan --name epel-disable provision --how $method prepare"
            rlAssertGrep 'Repo epel.*disabled' "$rlRun_LOG"

            rlRun -s "tmt run plan --name epel-enable provision " \
                     "--how $method prepare --how feature --epel disabled"
            rlAssertGrep 'Repo epel.*disabled' "$rlRun_LOG"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
