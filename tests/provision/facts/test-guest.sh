#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check $PROVISION_HOW plugin"
        if [ "$PROVISION_HOW" = "local" ]; then
            provision_options=""
            bfu_provision_options=""

            arch="$(arch)"

            if [ -f /etc/os-release ]; then
                distro="$(grep PRETTY_NAME /etc/os-release | cut -d'=' -f2 | tr -d '"')"
            else
                distro="$(cat /etc/redhat-release || cat /etc/fedora-release)"
            fi

            kernel="$(uname -r)"

            package_manager="dnf\|yum"

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

        elif [ "$PROVISION_HOW" = "container" ]; then
            provision_options="--image fedora:39"
            bfu_provision_options="$provision_options --user=nobody"

            arch="$(arch)"
            distro="Fedora Linux 39 (Container Image)"
            kernel="$(uname -r)"
            package_manager="dnf"

            grep "selinuxfs" /proc/filesystems &> /dev/null
            if [ $? -eq 1 ]; then
                selinux="no"
            else
                selinux="yes"
            fi

            is_superuser="yes"
            bfu_is_superuser="no"

        else
            rlDie "Provision method ${PROVISION_HOW} is not supported by the test."
        fi

        rlRun -s "tmt run -i $run --scratch     provision -h "$PROVISION_HOW" $provision_options plan -n /plans/features/core"

        rlAssertGrep "arch: $arch" $rlRun_LOG
        rlAssertGrep "distro: $distro" $rlRun_LOG
        rlAssertNotGrep "kernel: $kernel" $rlRun_LOG
        rlAssertNotGrep "package manager: $package_manager" $rlRun_LOG
        rlAssertNotGrep "selinux: $selinux" $rlRun_LOG
        rlAssertNotGrep "is superuser: " $rlRun_LOG

        rlRun -s "tmt run -i $run --scratch -vv provision -h "$PROVISION_HOW" $provision_options plan -n /plans/features/core"

        rlAssertGrep "arch: $arch" $rlRun_LOG
        rlAssertGrep "distro: $distro" $rlRun_LOG
        rlAssertGrep "kernel: $kernel" $rlRun_LOG
        rlAssertGrep "package manager: $package_manager" $rlRun_LOG
        rlAssertGrep "selinux: $selinux" $rlRun_LOG
        rlAssertGrep "is superuser: $is_superuser" $rlRun_LOG

        # If provisioning method allows a less privileged user, check that one as well
        if [ "$bfu_provision_options" != "" ]; then
            rlRun -s "tmt run -i $run --scratch -vv provision -h "$PROVISION_HOW" $bfu_provision_options plan -n /plans/features/core"

            rlAssertGrep "arch: $arch" $rlRun_LOG
            rlAssertGrep "distro: $distro" $rlRun_LOG
            rlAssertGrep "kernel: $kernel" $rlRun_LOG
            rlAssertGrep "package manager: $package_manager" $rlRun_LOG
            rlAssertGrep "selinux: $selinux" $rlRun_LOG
            rlAssertGrep "is superuser: $bfu_is_superuser" $rlRun_LOG
        fi

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
