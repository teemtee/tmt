#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

METHODS=${METHODS:-beaker}

SRC_PLAN="$(pwd)/data/plan.fmf"

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init"
    rlPhaseEnd

    rlPhaseStartTest "Try provision beaker with fedora image"
        if [ ! -f /etc/beaker/client.conf ] ; then
            rlRun "touch /etc/beaker/client.conf && file /etc/beaker/client.conf"
        fi
        rlRun "tmt run -i $run --scratch \
            plans --default finish login -c echo \
            provision -h beaker --image fedora" 2
            # exit code 2 is an error caused by missing kerberos credentials
            # Error message:
            # Beaker needs Kerberos ticket to authenticate to BeakerHub. Run 'kinit $USER' command to obtain Kerberos credentials.
        rlRun "cat $run/log.txt" 0 "Dump log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
