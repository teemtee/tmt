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

    rlPhaseStartTest 'fmf-id (w/ url): Show fmf ids for discovered tests'
        plan='plan --name fmf/url/ref/path'
        rlRun "tmt run -r $plan discover -h fmf --fmf-id finish | tee output"

        # check "discover --fmf-id" shows the same tests as "tmt run discover"
        rlRun "tmt run -v $plan discover | tee discover"
        tests_list=$(tac discover |
                     sed -n '/summary:/q;p')
        url_discover=$(grep "url:" discover | awk '{print $2}')

        for test in $tests_list; do
            rlAssertGrep "$test" output
        done

        ids_amount=$(grep -o -i "name:" output | wc -l)
        url_fmf_id=$(grep "url:" output | head -n 1 | awk '{print $2}')
        ref_fmf_id=$(grep "ref:" output | head -n 1 | awk '{print $2}')

        tests_amount=$(echo $tests_list | wc -w)
        rlAssertEquals "Check that number of fmf-ids equals to tests number" \
                       "$ids_amount" "$tests_amount"
        rlAssertEquals "Check url" "$url_discover" "$url_fmf_id"
        rlAssertEquals "Check ref" "HEAD" "$ref_fmf_id"
    rlPhaseEnd

    rlPhaseStartTest 'fmf-id (w/o url): Show fmf ids for discovered tests'
        plan='plan --name fmf/nourl/noref/nopath'
        rlRun "tmt run -dvvvr $plan discover -h fmf --fmf-id finish \
               | tee output"

        # check "discover --fmf-id" shows the same tests as "tmt run discover"
        tests_list=$(tmt run -v $plan discover |
                     tac |
                     sed -n '/summary:/q;p')
        for test in $tests_list; do
            rlAssertGrep "$test" output
        done

        # check path of "tmt test export --fmf-id"
        # is the same as "tmt run discover --fmf-id"
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
    rlPhaseStartTest "fmf-id (w/o url): all steps(discover, provision, etc.) \
                      are enabled"
        plan='plan --name fmf/nourl/noref/nopath'
        rlRun "tmt run -dvvvr --all $plan discover -h fmf --fmf-id | tail -n1 \
               | tee output"
        rlAssertGrep "path:" output
    rlPhaseEnd

    # If plan or test weren't explicitly specified then fmf-ids for all tests
    # in all plans should be shown
    rlPhaseStartTest "fmf-id (w/o url): plans were executed if plan/test -n=."
        ids_amount=$(tmt run -r discover -h fmf --fmf-id finish |
                     grep "name:" |
                     wc -l)
        tests_amount=$(tmt run -r discover -h fmf finish |
                       grep "summary:" |
                       awk '{print $2}' |
                       awk '{s+=$1} END {print s}')
        rlAssertEquals "Check that number of fmf-ids equals to tests number" \
                       "$ids_amount" "$tests_amount"
    rlPhaseEnd

    # Checking the case when fmf_root = git_root
    rlPhaseStartTest "fmf-id (w/o url): path doesn't shown up"
        path="$(git rev-parse --show-toplevel)"
        rlRun "cd $path"
        rlRun "tmt run -r test --name /tests/unit \
                          plans --default \
                          discover --how fmf --fmf-id finish | tee output"
        rlAssertNotGrep "path:" output
    rlPhaseEnd

#    # If the test exists in 2 or more plans than the test should be printed
#    # only once
#    rlPhaseStartTest "fmf-id: one test exists in 2 or more plans"
#        path="$(git rev-parse --show-toplevel)"
#        rlRun "cd $path"
#        ids_amount=$(tmt run -r discover --how fmf --fmf-id \
#                     tests --name /tests/unit |
#                     grep "name:" |
#                     wc -l)
#        tests_amount=1
#        rlAssertEquals "Check that number of fmf-ids equals to tests number" \
#                       "$ids_amount" "$tests_amount"
#    rlPhaseEnd

    rlPhaseStartTest "fmf-id (w/o url): check the test with --how=shell"
        path="$(git rev-parse --show-toplevel)"
        rlRun "cd $path/plans/sanity"
        rlRun "tmt run -r test --name /lint/plans \
                          plan --name /plans/sanity/lint \
                          discover -h shell --fmf-id finish 2>&1 | \
                          tee output" 2
        rlAssertGrep "Error: no such option: --fmf-id" output -i
    rlPhaseEnd

    # Raise an exception if --fmf-id uses w/o --url and git root doesn't exist
    rlPhaseStartTest "fmf-id (w/o url): and git root doesn't exist"
        tmp_dir="$(mktemp -d)"
        rlRun "cd $tmp_dir"
        rlRun "tmt init --template base"
        rlRun "tmt run -rdvvv discover -h fmf --fmf-id finish 2>&1 \
               | tee output" 2
        rlAssertGrep "\`tmt run discover --fmf-id\` without \`url\` option \
can be used only within git repo." output
        rlRun "rm -rf $tmp_dir"
    rlPhaseEnd

    # If in non-git directory exist plan w/ and w/o url, then only fmf-ids for
    # the plan w/ url should be reported
    rlPhaseStartTest "fmf-id (w/o and w/ url): non-git directory"
        plan="plan -n /plans/example"
        tmp_dir1="$(mktemp -d)"
        tmp_dir2="$(mktemp -d)"
        rlRun "cd $tmp_dir1"
        rlRun "tmt init --template full"
        rlRun "cd $tmp_dir2"
        rlRun "tmt init --template base"
        rlRun "cp plans/example.fmf $tmp_dir1/plans/non-url.fmf"
        rlRun "cd $tmp_dir1"
        # check "discover --fmf-id" shows the same tests as "tmt run discover"
        rlRun "tmt run -r discover -h fmf --fmf-id finish | tee output"
        rlRun "tmt run -v $plan discover | tee discover"
        tests_list=$(tac discover |
                     sed -n '/summary:/q;p')
        url_discover=$(grep "url:" discover | awk '{print $2}')

        for test in $tests_list; do
            rlAssertGrep "$test" output
        done

        ids_amount=$(grep -o -i "name:" output | wc -l)
        url_fmf_id=$(grep "url:" output | head -n 1 | awk '{print $2}')

        tests_amount=$(echo $tests_list | wc -w)
        rlAssertEquals "Check that number of fmf-ids equals to tests number" \
                       "$ids_amount" "$tests_amount"
        rlAssertEquals "Check url" "$url_discover" "$url_fmf_id"
        rlRun "rm -rf $tmp_dir1 $tmp_dir2"
    rlPhaseEnd

    # Raise an exception if current dir doesn't have .fmf
    rlPhaseStartTest "fmf-id (w/o url): current dir doesn't have fmf metadata"
        tmp_dir="$(mktemp -d)"
        rlRun "cd $tmp_dir"
        rlRun "tmt run -rdvvv discover -h fmf --fmf-id finish 2>&1 \
               | tee output" 2
        rlAssertGrep "No metadata found in the current directory" output
        rlRun "rm -rf $tmp_dir"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'rm -f output' 0 'Removing tmp file'
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
