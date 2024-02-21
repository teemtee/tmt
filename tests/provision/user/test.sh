#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Container, default user root"
        rlRun -s "tmt run -i $run -a provision --how $PROVISION_HOW report -vvv"
        rlAssertGrep "uid=0(root) gid=0(root) groups=0(root)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Container, set specific user"
        rlRun -s "tmt run --scratch -i $run -a provision --how $PROVISION_HOW --user nobody report -vvv"
        rlAssertGrep "uid=65534(nobody) gid=65534(nobody) groups=65534(nobody)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
