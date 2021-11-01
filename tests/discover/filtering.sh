#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'pushd data'
        rlRun 'set -o pipefail'
    rlPhaseEnd

    rlPhaseStartTest "Filter by test name"
        plan='plan --name fmf/nourl/noref/nopath'
        discover='discover --how fmf --test discover1'
        rlRun 'tmt run -dvr $discover $plan finish | tee output'
        rlAssertGrep '1 test selected' output
        rlAssertGrep '/tests/discover1' output
        rlAssertNotGrep '/tests/discover2' output
        rlAssertNotGrep '/tests/discover3' output
    rlPhaseEnd

    rlPhaseStartTest "Filter by advanced filter"
        plan='plan --name fmf/nourl/noref/nopath'
        discover='discover --how fmf --filter tier:1,2'
        rlRun 'tmt run -dvr $discover $plan finish | tee output'
        rlAssertGrep '2 tests selected' output
        rlAssertGrep '/tests/discover1' output
        rlAssertGrep '/tests/discover2' output
        rlAssertNotGrep '/tests/discover3' output
    rlPhaseEnd

    rlPhaseStartTest "Filter by link"
        plan='plans --default'
        for link_relation in "" "relates:" "rel.*:"; do
            discover="discover -h fmf --link ${link_relation}/tmp/foo"
            rlRun 'tmt run -dvr $discover $plan finish | tee output'
            rlAssertGrep '1 test selected' output
            rlAssertGrep '/tests/discover1' output
        done
        for link_relation in "verifies:https://github.com/teemtee/tmt/issues/870" \
            "ver.*:.*/issues/870" ".*/issues/870"; do
            discover="discover -h fmf --link $link_relation --link rubbish"
            rlRun "tmt run -dvr $discover $plan finish | tee output"
            rlAssertGrep '1 test selected' output
            rlAssertGrep '/tests/discover2' output
        done
    rlPhaseEnd

    rlPhaseStartTest 'fmf-id: Show fmf ids for tests discovered in plan'
        plan='plan --name fmf/nourl/noref/nopath'
        rlRun "tmt run -dvvvr $plan discover --fmf-id | tee output"

        # check "discover --fmf-id" shows the same tests as "tmt run discover"
        tests_list=$(tmt run -rv $plan discover | tac | sed -n '/summary:/q;p')
        for test in $tests_list; do
            rlAssertGrep "$test" output
        done

        # check path of "test export --fmf-id"
        # is the same as "discover --fmf-id"
        test1=$(echo $tests_list | awk '{print $1}')
        path=$(tmt test export $test1 --fmf-id |
               grep "path:" | awk '{print $2}')
        rlAssertGrep "$path" output

        ids_amount=$(grep -o -i "name:" output | wc -l)
        tests_amount=$(echo $tests_list | wc -w)
        rlAssertEquals "Check that number of fmf-ids equals to tests number" \
                       "$ids_amount" "$tests_amount"
    rlPhaseEnd

    # If the user runs all steps and customize discover with --fmf-id the test
    # should finish after discover part
    rlPhaseStartTest "fmf-id: all steps(discover, provision, etc.) are enabled"
        plan='plan --name fmf/nourl/noref/nopath'
        rlRun "tmt run -dvvvr --all $plan discover --fmf-id | tail -n1 \
               | tee output"
        rlAssertGrep "path:" output
    rlPhaseEnd

    rlPhaseStartTest "fmf-id: check the test with node.root=None"
        path="$(git rev-parse --show-toplevel)"
        rlRun "cd $path/plans/sanity"
        rlRun "tmt run -r test --name /lint/plans \
                          plan --name /plans/sanity/lint \
                          discover --fmf-id | grep path | tee output"
        rlAssertGrep "$path" output
    rlPhaseEnd

    # Checking the case when fmf_root = git_root
    rlPhaseStartTest "fmf-id: path doesn't shown up"
        path="$(git rev-parse --show-toplevel)"
        rlRun "cd $path"
        rlRun "tmt run -r test --name /tests/unit \
                          plans --default \
                          discover --how fmf --fmf-id | tee output"
        rlAssertNotGrep "path:" output
    rlPhaseEnd

    # If plan or test weren't explicitly specified then fmf-ids for all tests
    # in all plans should be shown
    rlPhaseStartTest "fmf-id: all plans were executed if plan/test -n=."
        path="$(git rev-parse --show-toplevel)"
        rlRun "cd $path"
        ids_amount=$(tmt run -r discover --fmf-id | grep "name:" | wc -l)
        tests_amount=$(tmt run -r discover |
                       grep "summary:" |
                       awk '{print $2}' |
                       awk '{s+=$1} END {print s}')
        rlAssertEquals "Check that number of fmf-ids equals to tests number" \
                       "$ids_amount" "$tests_amount"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'rm -f output' 0 'Removing tmp file'
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
