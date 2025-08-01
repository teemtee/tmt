#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test guest-specific SSH options with provision $PROVISION_HOW"
        rlRun "tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW --ssh-option ServerAliveCountMax=123456789"
        rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=123456789" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartTest "Test global SSH options with provision $PROVISION_HOW"
        rlRun "TMT_SSH_SERVER_ALIVE_COUNT_MAX=123456789 tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW"
        rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=123456789" "$run/log.txt"

        rlRun "TMT_SSH_ServerAliveCountMax=123456789 tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW"
        rlAssertGrep "Run command: ssh .*-oServeralivecountmax=123456789" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartTest "Test global SSH options occur first in ssh parameters $PROVISION_HOW"
      rlRun "TMT_SSH_SERVER_ALIVE_INTERVAL=7 TMT_SSH_SERVER_ALIVE_COUNT_MAX=9 tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW"
      # check that default and custom_ssh_options are present
      rlAssertGrep "Run command: ssh .*-oServerAliveInterval=7" "$run/log.txt"
      rlAssertGrep "Run command: ssh .*-oServerAliveInterval=5" "$run/log.txt"
      rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=60" "$run/log.txt"
      rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=9" "$run/log.txt"
      # check that custom_ssh_options occur before default ssh options
      rlAssertGrep "Run command: ssh .*-oServerAliveInterval=7.*-oServerAliveInterval=5" "$run/log.txt"
      rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=9.*-oServerAliveCountMax=60" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
