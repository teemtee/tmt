#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

# Check the expected output
function check() {
    # Space-separated test names on a single line
    tests=$(grep '^  */tests/' "$rlRun_LOG" | sed 's/^ *//' | tr '\n' ' ' | sed 's/ $//')
    rlAssertEquals "Check expected tests" "$tests" "$1"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        tmt="tmt run --id $run --scratch discover -v --how fmf"
        rlRun "pushd data"
    rlPhaseEnd

    # All tests

    rlPhaseStartTest "Select all available tests"
        rlRun -s "$tmt plan --name /plans/all"
        check "/tests/one /tests/two /tests/three /tests/four"
    rlPhaseEnd

    # The 'test' key

    rlPhaseStartTest "Select using the 'test' key"
        rlRun -s "$tmt plan --name /plans/test"
        check "/tests/three /tests/one /tests/three"
    rlPhaseEnd

    for option in '-t' '--test'; do
        rlPhaseStartTest "Select using the '$option' option"
            rlRun -s "$tmt $option three $option one $option three plan --name /plans/all"
            check "/tests/three /tests/one /tests/three"
        rlPhaseEnd
    done

    # The 'include' key

    rlPhaseStartTest "Select using the 'include' key"
        rlRun -s "$tmt plan --name /plans/include"
        check "/tests/one /tests/three"
    rlPhaseEnd

    for option in '-i' '--include'; do
        rlPhaseStartTest "Select using the '$option' option"
            rlRun -s "$tmt $option three $option one $option three plan --name /plans/all"
            check "/tests/one /tests/three"
        rlPhaseEnd
    done

    # The 'exclude' key

    rlPhaseStartTest "Select using the 'exclude' key"
        rlRun -s "$tmt plan --name /plans/exclude"
        check "/tests/two /tests/four"
    rlPhaseEnd

    for option in '-x' '--exclude'; do
        rlPhaseStartTest "Select using the '$option' option"
            rlRun -s "$tmt $option one $option three plan --name /plans/all"
            check "/tests/two /tests/four"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
