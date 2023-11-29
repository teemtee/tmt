#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

PROVISION_METHODS=${PROVISION_METHODS:-virtual}

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    for provision_method in $PROVISION_METHODS; do
        rlPhaseStartTest "Test with provision $provision_method - check defaults and edited ServerAliveCountMax"
            rlRun "tmt run --scratch -vvi $run -a provision -h $provision_method --ssh-option ServerAliveCountMax=123456789"
            rlAssertGrep "Run command: ssh .*-oForwardX11=no" "$run/log.txt"
            rlAssertGrep "Run command: ssh .*-oStrictHostKeyChecking=no" "$run/log.txt"
            rlAssertGrep "Run command: ssh .*-oUserKnownHostsFile=/dev/null" "$run/log.txt"
            rlAssertGrep "Run command: ssh .*-oServerAliveInterval=60" "$run/log.txt"
            rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=123456789" "$run/log.txt"
            rlAssertGrep "Run command: ssh .*-oLogLevel=QUIET" "$run/log.txt"
        rlPhaseEnd

        rlPhaseStartTest "Test with provision $provision_method - no LogLevel=QUIET with debug"
            rlRun "tmt run --scratch -dvvi $run -a provision -h $provision_method --ssh-option ServerAliveCountMax=123456789"
            rlAssertNotGrep "Run command: ssh .*-oLogLevel=QUIET" "$run/log.txt"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
