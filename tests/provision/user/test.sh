#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, default user root"
        rlRun -s "tmt run -i $run -a provision --how $PROVISION_HOW report -vvv"
        rlAssertGrep "uid=0(root) gid=0(root) groups=0(root)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "$PROVISION_HOW, set specific user"
        if [ "$PROVISION_HOW" = "virtual" ]; then
            user="fedora"
            ids="1000"
        else
            user="nobody"
            ids="65534"
        fi

        rlRun -s "tmt run --scratch -i $run -a provision --how $PROVISION_HOW --user $user report -vvv"
        rlAssertGrep "uid=$ids($user) gid=$ids($user) groups=$ids($user)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
