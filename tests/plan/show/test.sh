#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

function dump_fmf_id_block
{
    typeset output=${1?"*** output file"}
    typeset lineno=$(cat -n $output | egrep 'fmf-id' | awk '{print $1}')
    sed -n "$lineno,$"p $output
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "output=\$(mktemp)"
        rlRun "show_tmp=\$(mktemp)"
        rlRun "show_dir1=\$(mktemp -d)"
        rlRun "show_dir2=\$(mktemp -d)"
        rlRun "show_dir3=\$(mktemp -d)"
    rlPhaseEnd

    rlPhaseStartTest "Show a plan with -vvv in a normal git repo"
        rlRun -s "tmt plans show -vvv mini"
        dump_fmf_id_block $rlRun_LOG > $show_tmp
        rlRun "cat $show_tmp"
        rlAssertGrep "url:" $show_tmp
        rlAssertGrep "ref:" $show_tmp
        rlAssertGrep "path:" $show_tmp
        rlAssertGrep "name:" $show_tmp
        rlAssertGrep "web" $show_tmp
    rlPhaseEnd

    rlPhaseStartTest "Show a plan with -vvv in an empty git repo"
        rlRun "pushd $show_dir1"
        rlRun "git init ."
        rlRun "tmt init -t mini"
        rlRun -s "tmt plans show -vvv"
        dump_fmf_id_block $rlRun_LOG > $show_tmp
        rlRun "cat $show_tmp"
        rlAssertNotGrep "url:" $show_tmp
        rlAssertNotGrep "ref:" $show_tmp
        rlAssertNotGrep "path:" $show_tmp
        rlAssertGrep "name:" $show_tmp
        rlAssertNotGrep "web" $show_tmp
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Show a plan with -vvv in non-git repo"
        rlRun "pushd $show_dir2"
        rlRun "tmt init -t mini"
        rlRun -s "tmt plans show -vvv"
        dump_fmf_id_block $rlRun_LOG > $show_tmp
        rlRun "cat $show_tmp"
        rlAssertNotGrep "url:" $show_tmp
        rlAssertNotGrep "ref:" $show_tmp
        rlAssertNotGrep "path:" $show_tmp
        rlAssertGrep "name:" $show_tmp
        rlAssertNotGrep "web" $show_tmp
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Show a plan with -vvv in work tree"
        local_repo="$show_dir3/tmt"
        plan="/plans/sanity/lint"
        worktree="TREE"
        ref="myref"

        rlRun "git clone https://github.com/teemtee/tmt $local_repo"
        rlRun "pushd $local_repo"
        # fmf id fields should be shown when under the default branch
        rlRun -s "tmt plan show $plan -vvv"
        dump_fmf_id_block $rlRun_LOG > $show_tmp
        rlRun "cat $show_tmp"
        rlAssertGrep "url:" $show_tmp
        rlAssertGrep "ref:" $show_tmp
        rlAssertGrep "name:" $show_tmp
        # fmf id fields should be shown when under a different branch, too
        rlRun -s "git checkout -b another-branch"
        rlRun -s "tmt plan show $plan -vvv"
        dump_fmf_id_block $rlRun_LOG > $show_tmp
        rlRun "cat $show_tmp"
        rlAssertGrep "url:" $show_tmp
        rlAssertGrep "ref: another-branch" $show_tmp
        rlAssertGrep "name:" $show_tmp
        # Create a new worktree
        rlRun "git branch $ref"
        rlRun "git worktree add $worktree $ref"
        rlRun "popd"

        rlRun "pushd $local_repo/$worktree"
        rlRun -s "tmt plan show $plan -vvv"
        dump_fmf_id_block $rlRun_LOG > $show_tmp
        rlRun "cat $show_tmp"
        rlAssertGrep "url:" $show_tmp
        rlAssertGrep "ref:.*$ref" $show_tmp
        rlAssertGrep "name:" $show_tmp
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Show a minimal plan"
        rlRun -s "tmt plans show mini"
        rlAssertGrep "how tmt" $rlRun_LOG
        rlAssertGrep "script /bin/true" $rlRun_LOG
        rlAssertGrep "enabled true" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Show a full plan"
        rlRun -s "tmt plans show -v full"
        # Core
        rlAssertGrep "summary Plan keys are correctly displayed" $rlRun_LOG
        rlAssertGrep "description Some description" $rlRun_LOG
        rlAssertGrep "contact Some Body <somebody@somewhere.org>" $rlRun_LOG
        rlAssertGrep "id e3a9a8ed-4585-4e86-80e8-1d99eb5345a9" $rlRun_LOG
        rlAssertGrep "enabled true" $rlRun_LOG
        rlAssertGrep "order 70" $rlRun_LOG
        rlAssertGrep "tag foo" $rlRun_LOG
        rlAssertGrep "tier 3" $rlRun_LOG
        rlAssertGrep "relates https://something.org/related" $rlRun_LOG

        # Steps
        rlRun "grep -Pzo '(?sm)^ *discover ?$.*^ *provision' $rlRun_LOG > $output"
        rlAssertGrep "    how fmf" $output
        rlAssertGrep "    filter tier:1" $output
        rlRun "grep -Pzo '(?sm)^ *provision ?$.*^ *prepare' $rlRun_LOG > $output"
        rlAssertGrep "    how container" $output
        rlAssertGrep "    image fedora" $output
        rlRun "grep -Pzo '(?sm)^ *prepare ?$.*^ *report' $rlRun_LOG > $output"
        rlAssertGrep "    how shell" $output
        rlAssertGrep "    script systemctl start libvirtd" $output
        rlRun "grep -Pzo '(?sm)^ *report ?$.*^ *finish' $rlRun_LOG > $output"
        rlAssertGrep "    how html" $output
        rlAssertGrep "    open true" $output
        rlRun "grep -A30 '^ *finish' $rlRun_LOG > $output"
        rlAssertGrep "    how ansible" $output
        rlAssertGrep "    playbook cleanup.yaml" $output

        # Extra
        rlAssertGrep "environment KEY: VAL" $rlRun_LOG
        rlAssertGrep "context distro: fedora" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "List all plans by default"
        rlRun -s "tmt plans ls"
        rlAssertGrep "/plans/enabled" $rlRun_LOG
        rlAssertGrep "/plans/disabled" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "List only enabled plans"
        rlRun -s "tmt plans ls --enabled"
        rlAssertGrep "/plans/enabled" $rlRun_LOG
        rlAssertNotGrep "/plans/disabled" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "List only disabled plans"
        rlRun -s "tmt plans ls --disabled"
        rlAssertNotGrep "/plans/enabled" $rlRun_LOG
        rlAssertGrep "/plans/disabled" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Show all plans by default"
        rlRun -s "tmt plans show"
        rlAssertGrep "/plans/enabled" $rlRun_LOG
        rlAssertGrep "/plans/disabled" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Show only enabled plans"
        rlRun -s "tmt plans show --enabled"
        rlAssertGrep "/plans/enabled" $rlRun_LOG
        rlAssertGrep "enabled true" $rlRun_LOG
        rlAssertNotGrep "/plans/disabled" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Show only disabled plans"
        rlRun -s "tmt plans show --disabled"
        rlAssertNotGrep "/plans/enabled" $rlRun_LOG
        rlAssertGrep "/plans/disabled" $rlRun_LOG
        rlAssertGrep "enabled false" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Show and honor envvars"
        rlRun -s "tmt plan show /plans/envvars" 0 "Show plan"
        rlAssertEquals "script shall be an envvar" "$(grep ' script ' $rlRun_LOG | awk '{print $2}')" "\$ENV_SCRIPT"

        rlRun -s "tmt plan show -e ENV_SCRIPT=dummy-script /plans/envvars" 0 "Export plan"
        rlAssertEquals "script shall be an replaced" "$(grep ' script ' $rlRun_LOG | awk '{print $2}')" "dummy-script"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm $output"
        rlRun "rm -rf $show_tmp $show_dir1 $show_dir2 $show_dir3"
    rlPhaseEnd
rlJournalEnd
