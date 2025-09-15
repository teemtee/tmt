#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

USER="tester-$$"

function user_cleanup {
    local user="$1"
    rlRun "pkill -u $user" 0,1
    # user session might be doing scripts
    command -v loginctl >/dev/null && rlRun "loginctl terminate-user $user" 0,1
    rlRun "userdel -r $user"
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "tmt init"
        cat <<EOF > plan.fmf
provision:
    how: local
execute:
    how: tmt
    script: echo
EOF
        rlRun "chmod 777 -R $tmp"
        rlRun "set -o pipefail"

        rlRun "useradd $USER"

        rlRun "tmp_workdirs=\$(mktemp -d)" 0 "Create another tmp directory for TMT_WORKDIR_ROOT"
        rlRun "chmod 755 $tmp_workdirs" 0 "Make sure the TMT_WORKDIR_ROOT base is accessible by all users"
    rlPhaseEnd

    rlPhaseStartTest "Recreated correctly"
        rlRun "WORKDIR_ROOT=$tmp_workdirs/create" 0 "Set WORKDIR_ROOT for current test case"
        rlRun "TMT_WORKDIR_ROOT=$WORKDIR_ROOT tmt run"
        rlAssertEquals "Correct permission" "$(stat --format '%a' $WORKDIR_ROOT)" "1777"
        # Another user can use WORKDIR_ROOT
        rlRun "su -l -c 'cd $tmp; TMT_WORKDIR_ROOT=$WORKDIR_ROOT tmt --feeling-safe run' '$USER'"
    rlPhaseEnd


    rlPhaseStartCleanup
        rlRun "popd"
        user_cleanup "$USER"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
        rlRun "rm -r $tmp_workdirs" 0 "Removing TMT_WORKDIR_ROOT"
    rlPhaseEnd
rlJournalEnd
