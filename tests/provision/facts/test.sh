#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check $provision_method plugin"
        if [ -f /etc/os-release ]; then
            distro="$(grep PRETTY_NAME /etc/os-release | cut -d'=' -f2 | tr -d '"')"
        else
            distro="$(cat /etc/redhat-release || cat /etc/fedora-release)"
        fi

        if [ grep "selinuxfs" /proc/filesystems ]; then
            selinux="no"
        else
            selinux="yes"
        fi

        rlRun -s "tmt run -i $run --scratch     provision -h local plan -n /plans/features/core"

        rlAssertGrep "arch: $(arch)" $rlRun_LOG
        rlAssertGrep "distro: $distro" $rlRun_LOG
        rlAssertNotGrep "kernel: $(uname -r)" $rlRun_LOG
        rlAssertNotGrep "package manager: dnf\|yum" $rlRun_LOG
        rlAssertNotGrep "selinux: $selinux" $rlRun_LOG

        rlRun -s "tmt run -i $run --scratch -vv provision -h local plan -n /plans/features/core"

        rlAssertGrep "arch: $(arch)" $rlRun_LOG
        rlAssertGrep "distro: $distro" $rlRun_LOG
        rlAssertGrep "kernel: $(uname -r)" $rlRun_LOG
        rlAssertGrep "package manager: dnf\|yum" $rlRun_LOG
        rlAssertGrep "selinux: $selinux" $rlRun_LOG

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
