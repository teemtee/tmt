#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for provision_method in ${PROVISION_METHODS:-local}; do
        rlPhaseStartTest "Check $provision_method plugin"
            if [ "$provision_method" = "local" ]; then
                if [ -f /etc/os-release ]; then
                    distro="$(grep PRETTY_NAME /etc/os-release | cut -d'=' -f2 | tr -d '"')"
                else
                    distro="$(cat /etc/redhat-release || cat /etc/fedora-release)"
                fi

                grep "selinuxfs" /proc/filesystems &> /dev/null
                if [ $? -eq 1 ]; then
                    selinux="no"
                else
                    selinux="yes"
                fi
            fi

            rlRun -s "tmt run -i $run --scratch     provision -h "$provision_method" plan -n /plans/features/core"

            rlAssertGrep "arch: $(arch)" $rlRun_LOG
            rlAssertGrep "distro: $distro" $rlRun_LOG
            rlAssertNotGrep "kernel: $(uname -r)" $rlRun_LOG
            rlAssertNotGrep "package manager: dnf\|yum" $rlRun_LOG
            rlAssertNotGrep "selinux: $selinux" $rlRun_LOG

            rlRun -s "tmt run -i $run --scratch -vv provision -h "$provision_method" plan -n /plans/features/core"

            rlAssertGrep "arch: $(arch)" $rlRun_LOG
            rlAssertGrep "distro: $distro" $rlRun_LOG
            rlAssertGrep "kernel: $(uname -r)" $rlRun_LOG
            rlAssertGrep "package manager: dnf\|yum" $rlRun_LOG
            rlAssertGrep "selinux: $selinux" $rlRun_LOG
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
