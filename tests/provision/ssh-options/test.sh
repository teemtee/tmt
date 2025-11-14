#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

#    rlPhaseStartTest "Test guest-specific SSH options with provision $PROVISION_HOW"
#        rlRun "tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW --ssh-option ServerAliveCountMax=123456789"
#        rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=123456789" "$run/log.txt"
#    rlPhaseEnd
#
#    rlPhaseStartTest "Test global SSH options with provision $PROVISION_HOW"
#        rlRun "TMT_SSH_SERVER_ALIVE_COUNT_MAX=123456789 tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW"
#        rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=123456789" "$run/log.txt"
#
#        rlRun "TMT_SSH_ServerAliveCountMax=123456789 tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW"
#        rlAssertGrep "Run command: ssh .*-oServeralivecountmax=123456789" "$run/log.txt"
#    rlPhaseEnd
#
#    rlPhaseStartTest "Test global SSH options occur first in ssh parameters $PROVISION_HOW"
#      rlRun "TMT_SSH_SERVER_ALIVE_INTERVAL=7 TMT_SSH_SERVER_ALIVE_COUNT_MAX=9 tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW"
#      # check that default and custom_ssh_options are present
#      rlAssertGrep "Run command: ssh .*-oServerAliveInterval=7" "$run/log.txt"
#      rlAssertGrep "Run command: ssh .*-oServerAliveInterval=5" "$run/log.txt"
#      rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=60" "$run/log.txt"
#      rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=9" "$run/log.txt"
#      # check that custom_ssh_options occur before default ssh options
#      rlAssertGrep "Run command: ssh .*-oServerAliveInterval=7.*-oServerAliveInterval=5" "$run/log.txt"
#      rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=9.*-oServerAliveCountMax=60" "$run/log.txt"
#    rlPhaseEnd
#
    rlPhaseStartTest "Test SSH config file option with provision $PROVISION_HOW"
        rlRun "ssh_config_file=\$(mktemp)" 0 "Create SSH config file"
        rlRun "echo 'Host *' > \$ssh_config_file"
        rlRun "echo '  ServerAliveCountMax 987654321' >> \$ssh_config_file"

        # Test explicit SSH config file via --ssh-config-file option
        rlRun "tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW --ssh-config-file \$ssh_config_file"
        rlAssertGrep "Run command: ssh .*-F.*$ssh_config_file" "$run/log.txt"

        rlRun "rm -f \$ssh_config_file" 0 "Remove SSH config file"
    rlPhaseEnd

    rlPhaseStartTest "Test default SSH config file under TMT_CONFIG_DIR with provision $PROVISION_HOW"
        rlRun "config_dir=\$(mktemp -d)" 0 "Create config directory"
        rlRun "ssh_config_path=\$config_dir/ssh_config"
        rlRun "echo 'Host *' > \$ssh_config_path"
        rlRun "echo '  ServerAliveCountMax 555444333' >> \$ssh_config_path"

        # Test default SSH config file via TMT_CONFIG_DIR
        rlRun "TMT_CONFIG_DIR=\$config_dir tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW"
        rlAssertGrep "Run command: ssh .*-F.*\$ssh_config_path" "$run/log.txt"

        rlRun "rm -rf \$config_dir" 0 "Remove config directory"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
