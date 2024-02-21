#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create run directory"
        rlRun "cp -a data $tmp"
        rlRun "pushd $tmp/data"
        rlRun "git init"
    rlPhaseEnd

    # url + keep-git-metadata:false (default)
    # is tested by /tests/discover/references/shell

    plan=/url/keep
    rlPhaseStartTest "$plan"
        rlRun "tmt run --id $tmp/u_k --keep plan -n $plan" 0
    rlPhaseEnd

    plan=/local/default
    rlPhaseStartTest "$plan"
        rlRun "tmt run --id $tmp/l_d --keep plan -n $plan" 0
    rlPhaseEnd

    plan=/local/keep
    rlPhaseStartTest "$plan"
        rlRun "tmt run --id $tmp/l_k --keep plan -n $plan" 0
    rlPhaseEnd

    rlPhaseStartTest "git root is parent of fmf root"
        rlRun "git_repo=\$(mktemp -d)"
        rlRun "mkdir $git_repo/fmf_root"
        rlRun "cp $tmp/data/plan.fmf $git_repo/fmf_root"
        rlRun "pushd $git_repo && git init"
        rlRun "pushd fmf_root && tmt init"
        rlRun -s "tmt run --id $tmp/gr --keep plan -n /local/keep" 2
        rlAssertGrep "keep-git-metadata.*can be used only" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd && popd && popd"
        rlRun "rm -rf $tmp $git_repo" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
