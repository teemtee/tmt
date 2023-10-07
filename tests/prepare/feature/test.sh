#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    for method in ${PROVISION_METHODS:-"container"}; do
	# EPEL
        rlPhaseStartTest "Enable EPEL"
            rlRun -s "tmt run --all plan --name epel-enable provision --how $method"
            rlAssertGrep 'Repo epel.*enabled' "$rlRun_LOG"

            rlRun -s "tmt run --all plan --name epel-disable provision " \
                     "--how $method prepare --how feature --epel enabled"
            rlAssertGrep 'Repo epel.*enabled' "$rlRun_LOG"
        rlPhaseEnd

        rlPhaseStartTest "Disable EPEL"
            rlRun -s "tmt run --all plan --name epel-disable provision --how $method"
            rlAssertGrep 'Repo epel.*disabled' "$rlRun_LOG"

            rlRun -s "tmt run --all plan --name epel-enable provision " \
                     "--how $method prepare --how feature --epel disabled"
            rlAssertGrep 'Repo epel.*disabled' "$rlRun_LOG"
        rlPhaseEnd

	# FIPS
        rlPhaseStartTest "Enable FIPS"
            rlRun -s "tmt run --all plan --name fips-enable provision --how $method prepare"

            rlRun -s "tmt run --all plan --name fips-disable provision " \
                     "--how $method prepare --how feature --fips enabled"
        rlPhaseEnd

        rlPhaseStartTest "Disable FIPS"
            rlRun -s "tmt run --all plan --name fips-disable provision --how $method prepare"

            rlRun -s "tmt run --all plan --name epel-enable provision " \
                     "--how $method prepare --how feature --fips disabled"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
