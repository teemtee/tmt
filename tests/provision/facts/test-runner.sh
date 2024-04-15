#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check host facts"
        arch="$(arch)"

        if [ -f /etc/os-release ]; then
            distro="$(grep PRETTY_NAME /etc/os-release | cut -d'=' -f2 | tr -d '"')"
        else
            distro="$(cat /etc/redhat-release || cat /etc/fedora-release)"
        fi

        kernel="$(uname -r)"

	package_manager="\(dnf\|dnf5\|yum\)"

        grep "selinuxfs" /proc/filesystems &> /dev/null
        if [ $? -eq 1 ]; then
            selinux="no"
        else
            selinux="yes"
        fi

        if [ "$(whoami)" != "root" ]; then
            is_superuser="no"
        else
            is_superuser="yes"
        fi

        rlRun -s "tmt run -i $run --scratch -dd  report plan -n /plans/features/core" 3

        rlAssertNotGrep "arch: $arch" $rlRun_LOG
        rlAssertNotGrep "distro: $distro" $rlRun_LOG
        rlAssertNotGrep "kernel: $kernel" $rlRun_LOG
        rlAssertNotGrep "package manager: $package_manager" $rlRun_LOG
        rlAssertNotGrep "selinux: $selinux" $rlRun_LOG
        rlAssertNotGrep "is superuser: $is_superuser" $rlRun_LOG

        rlRun -s "tmt run -i $run --scratch -ddd report plan -n /plans/features/core" 3

        rlAssertGrep "arch: $arch" $rlRun_LOG
        rlAssertGrep "distro: $distro" $rlRun_LOG
        rlAssertGrep "kernel: $kernel" $rlRun_LOG
        rlAssertGrep "package manager: $package_manager" $rlRun_LOG
        rlAssertGrep "selinux: $selinux" $rlRun_LOG
        rlAssertGrep "is superuser: $is_superuser" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
