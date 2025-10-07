#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "output=\$(mktemp)" 0 "Create output file"
        rlRun "set -o pipefail"
        rlRun "pushd data"
    rlPhaseEnd

    # Select by name
    for tmt in 'tmt test ls' 'tmt test show'; do
        rlPhaseStartTest "$tmt"
            rlRun "$tmt | grep -v 'warn: ' | tee $output"
            rlAssertGrep "/tests/enabled/default" $output
            rlAssertGrep "/tests/tag/default" $output
            rlAssertGrep "/tests/tier/default" $output
        rlPhaseEnd

        rlPhaseStartTest "$tmt <name>"
            rlRun "$tmt tier | grep -v 'warn: ' | tee $output"
            rlAssertNotGrep "/tests/enabled/default" $output
            rlAssertNotGrep "/tests/tag/default" $output
            rlAssertGrep "/tests/tier/default" $output
        rlPhaseEnd

        rlPhaseStartTest "$tmt non-existent"
            rlRun "$tmt non-existent | tee $output"
            rlRun "[[ $(wc -l <$output) == 0 ]]" 0 "Check no output"
        rlPhaseEnd
    done

    for name in '-n' '--name'; do
        rlPhaseStartTest "tmt run test $name <name>"
            tmt='tmt run -rv discover finish'
            # Existing
            rlRun "$tmt test $name enabled 2>&1 >/dev/null | grep -v 'warn: ' | tee $output"
            rlAssertGrep "/tests/enabled/default" $output
            rlAssertNotGrep "/tests/enabled/disabled" $output
            rlAssertNotGrep "/tests/tag/default" $output
            rlAssertNotGrep "/tests/tier/default" $output
            # Missing
            rlRun "$tmt test $name non-existent 2>&1 >/dev/null | grep -v 'warn: ' | tee $output"
            rlAssertGrep "No tests found" $output
            # Using 'test --name' overrides 'test' in discover
            rlRun "$tmt test $name tier/one 2>&1 >/dev/null | grep -v 'warn: ' | tee $output"
            rlAssertGrep "/tests/tier/one" $output
            rlAssertNotGrep "/tests/tier/two" $output
        rlPhaseEnd
    done

    rlPhaseStartTest "Select tests using a filter"
        # Enabled
        for bool in True true; do
            rlRun "tmt test ls --filter enabled:$bool | grep -v 'warn: ' | tee $output"
            rlAssertGrep '/tests/enabled/default' $output
            rlAssertGrep '/tests/enabled/defined' $output
            rlAssertNotGrep '/tests/enabled/disabled' $output
        done
        for bool in False false; do
            rlRun "tmt test ls --filter enabled:False | grep -v 'warn: ' | tee $output"
            rlAssertNotGrep '/tests/enabled/default' $output
            rlAssertNotGrep '/tests/enabled/defined' $output
            rlAssertGrep '/tests/enabled/disabled' $output
        done

        for tmt in 'tmt test ls' \
            'tmt run -rv discover finish test' \
            'tmt run -rv plans --name /plans/filtered discover finish test'; do

            if [[ "$tmt" == *" run "* ]]; then
                redirect="2>&1 >/dev/null"
            else
                redirect=""
            fi

            # Tag
            rlRun "$tmt --filter tag:slow $redirect | grep -v 'warn: ' | tee $output"
            rlAssertNotGrep '/tests/tag/default' $output
            rlAssertGrep '/tests/tag/defined' $output
            rlAssertNotGrep '/tests/tag/empty' $output
            rlRun "$tmt --filter tag:-slow $redirect | grep -v 'warn: ' | tee $output"
            rlAssertGrep '/tests/enabled/default' $output
            rlAssertNotGrep '/tests/tag/defined' $output
            rlAssertGrep '/tests/tag/empty' $output

            # Tier
            rlRun "$tmt --filter tier:1 $redirect | grep -v 'warn: ' | tee $output"
            rlAssertGrep '/tests/tier/one' $output
            rlAssertNotGrep '/tests/tier/two' $output
            rlAssertNotGrep '/tests/tier/default' $output
            rlRun "$tmt --filter tier:-1 $redirect | grep -v 'warn: ' | tee $output"
            rlAssertNotGrep '/tests/tier/one' $output
            rlAssertGrep '/tests/tier/two' $output
            rlAssertGrep '/tests/tier/default' $output
            rlRun "$tmt --filter tier:1,2 $redirect | grep -v 'warn: ' | tee $output"
            rlAssertGrep '/tests/tier/one' $output
            rlAssertGrep '/tests/tier/two' $output
            rlAssertNotGrep '/tests/tier/default' $output
            rlRun "$tmt -f tier:-1 -f tier:-2 $redirect | grep -v 'warn: ' | tee $output"
            rlAssertNotGrep '/tests/tier/one' $output
            rlAssertNotGrep '/tests/tier/two' $output
            rlAssertGrep '/tests/tier/default' $output
        done
    rlPhaseEnd

    rlPhaseStartTest "Select tests using a condition"
        # Enabled
        rlRun "tmt test ls --condition 'enabled == True' | grep -v 'warn: ' | tee $output"
        rlAssertGrep '/tests/enabled/default' $output
        rlAssertGrep '/tests/enabled/defined' $output
        rlAssertNotGrep '/tests/enabled/disabled' $output
        rlRun "tmt test ls --condition 'enabled == False' | grep -v 'warn: ' | tee $output"
        rlAssertNotGrep '/tests/enabled/default' $output
        rlAssertNotGrep '/tests/enabled/defined' $output
        rlAssertGrep '/tests/enabled/disabled' $output

        for tmt in 'tmt test ls' 'tmt run -rv discover finish test'; do
            if [[ "$tmt" == *" run "* ]]; then
                redirect="2>&1 >/dev/null"
            else
                redirect=""
            fi

            # Tag
            rlRun "$tmt --condition '\"slow\" in tag' $redirect | grep -v 'warn: ' | tee $output"
            rlAssertNotGrep '/tests/tag/default' $output
            rlAssertGrep '/tests/tag/defined' $output
            rlAssertNotGrep '/tests/tag/empty' $output
            rlRun "$tmt --condition '\"slow\" not in tag' $redirect | grep -v 'warn: ' | tee $output"
            rlAssertGrep '/tests/enabled/default' $output
            rlAssertNotGrep '/tests/tag/defined' $output
            rlAssertGrep '/tests/tag/empty' $output

            # Tier
            rlRun "$tmt --condition 'tier is not None' $redirect | grep -v 'warn: ' | tee $output"
            rlAssertGrep '/tests/tier/one' $output
            rlAssertGrep '/tests/tier/two' $output
            rlAssertNotGrep '/tests/tier/default' $output
            rlRun "$tmt -c 'tier and int(tier) > 1' $redirect | grep -v 'warn: ' | tee $output"
            rlAssertNotGrep '/tests/tier/one' $output
            rlAssertGrep '/tests/tier/two' $output
            rlAssertNotGrep '/tests/tier/default' $output
        done
    rlPhaseEnd

    rlPhaseStartTest "Select duplicate tests preserving tests ordering"
        # 'tmt test ls' lists test name once
        rlRun "tmt tests ls tier | grep -v 'warn: ' | tee $output"
        rlAssertGrep '/tests/tier/two' $output
        rlAssertEquals "/tests/tier/two is listed only once" 1 $( grep -c 'tier/two' $output )

        rlRun "tmt tests ls tier/two tier/two | grep -v 'warn: ' | tee $output"
        rlAssertGrep '/tests/tier/two' $output
        rlAssertEquals "/tests/tier/two is listed only once" 1 $( grep -c 'tier/two' $output )

        # 'tmt test show' lists test name once
        rlRun "tmt tests show tier | grep -v 'warn: ' | tee $output"
        rlAssertGrep '/tests/tier/two' $output
        rlAssertEquals "/tests/tier/two is listed only once" 1 $( grep -c 'tier/two' $output )

        # Prepare run dir and common command line
        run=$(mktemp -d)
        tmt="tmt run --id $run --scratch plans --name duplicate discover -v"

        # 'tmt run discover' lists duplicate test names preserving order
        rlRun "$tmt 2>&1 >/dev/null | grep -v 'warn: ' | tee $output"
        rlAssertGrep 'tests: /tier/two, /tier/one and /tier/two' $output
        rlAssertGrep 'summary: 3 tests selected' $output
        rlRun "grep -A 1 summary $output | tail -1 | grep '/tests/tier/two'"
        rlRun "grep -A 2 summary $output | tail -1 | grep '/tests/tier/one'"
        rlRun "grep -A 3 summary $output | tail -1 | grep '/tests/tier/two'"

        # tests --name filters discovered test names (/two is discovered twice)
        rlRun "$tmt -h fmf tests --name two 2>&1 >/dev/null | grep -v 'warn: ' | tee $output"
        rlAssertGrep 'tests: /tier/two, /tier/one and /tier/two' $output
        rlAssertGrep 'summary: 2 tests selected' $output
        rlRun "grep -A 1 summary $output | tail -1 | grep '/tests/tier/two'"
        rlRun "grep -A 2 summary $output | tail -1 | grep '/tests/tier/two'"

        # tests --name doesn't effect order of discovered tests
        rlRun "$tmt -h fmf tests --name one --name two 2>&1 >/dev/null | grep -v 'warn: ' | tee $output"
        rlAssertGrep 'tests: /tier/two, /tier/one and /tier/two' $output
        rlAssertGrep 'summary: 3 tests selected' $output
        rlRun "grep -A 1 summary $output | tail -1 | grep '/tests/tier/two'"
        rlRun "grep -A 2 summary $output | tail -1 | grep '/tests/tier/one'"
        rlRun "grep -A 3 summary $output | tail -1 | grep '/tests/tier/two'"

        # discover --test redefines duplicate plan so two is discovered just once
        rlRun "$tmt -h fmf --test two 2>&1 >/dev/null | grep -v 'warn: ' | tee $output"
        rlAssertGrep 'tests: two' $output
        rlAssertGrep 'summary: 1 test selected' $output
        rlRun "grep -A 1 summary $output | tail -1 | grep '/tests/tier/two'"

        # redefine --test via command line same as was in the plan
        rlRun "$tmt -h fmf --test two --test two 2>&1 >/dev/null | grep -v 'warn: ' | tee $output"
        rlAssertGrep 'tests: two and two' $output
        rlAssertGrep 'summary: 2 tests selected' $output
        rlRun "grep -A 1 summary $output | tail -1 | grep '/tests/tier/two'"
        rlRun "grep -A 2 summary $output | tail -1 | grep '/tests/tier/two'"

        # Clean up the run
        rlRun "rm -rf $run" 0 "Clean up run"
    rlPhaseEnd

    rlPhaseStartTest "Select by test --name . "
        rlRun "pushd subdir"
        run=$(mktemp -d)

        rlRun "tmt -c subdir=1 run --id $run discover tests --name ."
        # only /subdir test is selected by /plans/all and /plans/filtered
        for plan in all filtered; do
            rlRun "yq -o yaml -e '.[] | select(.name == \"/subdir\")' $run/plans/$plan/discover/tests.yaml" \
                0 "just /subdir in $plan"
        done
        # other two plans don't select any test
        for plan in duplicate selected; do
            rlAssertEquals "no test selected in $plan" \
                "$(cat $run/plans/$plan/discover/tests.yaml)" "[]"
        done

        rlRun "rm -rf $run" 0 "Clean up run"

        # Common prefix should not be selected
        rlRun -s "tmt tests ls . | grep -v 'warn: '"
        rlAssertGrep "/subdir" "$rlRun_LOG"
        rlAssertNotGrep "/subdir_other" "$rlRun_LOG"

        # Now get out of "subdir"
        rlRun "popd"

        # Virtual cases defined in /sub/ (no other tests should be selected)
        rlRun "pushd sub"
        rlRun -s "tmt tests ls .| grep -v 'warn: '"
        rlAssertGrep "/sub/first" "$rlRun_LOG"
        rlAssertGrep "/sub/second" "$rlRun_LOG"
        rlAssertNotGrep "/subdir" "$rlRun_LOG"
        rlRun "popd"

        # In top dir all tests should be selected
        rlRun -s "tmt tests ls .| grep -v 'warn: '"
        rlAssertGrep "/sub/first" "$rlRun_LOG"
        rlAssertGrep "/subdir" "$rlRun_LOG"
        rlAssertGrep "/tests" "$rlRun_LOG"
    rlPhaseEnd

    for exclude in '-x' '--exclude'; do
        rlPhaseStartTest "tmt test ls $exclude <regex>"
            rlRun "tmt test ls | grep -v 'warn: ' | tee $output"
            rlAssertGrep "/tests/enabled/default" $output
            rlRun "tmt test ls $exclude default | grep -v 'warn: ' | tee $output"
            rlAssertNotGrep "/tests/enabled/default" $output
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm $output" 0 "Remove output file"
    rlPhaseEnd
rlJournalEnd
