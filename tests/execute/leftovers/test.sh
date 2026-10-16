#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

WARNING="tmt: warning: processes started by the script still hold its output open"

# Run a test and check it finished well before its duration.
run_test() {
    local name="$1" expected="$2"

    SECONDS=0
    rlRun -s "tmt run --scratch -vvv -i $tmp -a provision -h $PROVISION_HOW test --name $name" "$expected"
    rlAssertGreater "Test $name should finish well before its duration" 60 $SECONDS
}

# Find the output of a test.
test_output() {
    find $tmp -path "*/execute/data/guest/*$1-*/output.txt" | head -1
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Leftover process, test passes"
        run_test /test/pass 0
        rlAssertGrep "pass /test/pass" $rlRun_LOG
        rlAssertGrep "^end$" "$(test_output pass)"
        rlAssertGrep "$WARNING" "$(test_output pass)" -F
    rlPhaseEnd

    rlPhaseStartTest "Leftover process, test fails"
        run_test /test/fail 1
        rlAssertGrep "fail /test/fail" $rlRun_LOG
        rlAssertGrep "$WARNING" "$(test_output fail)" -F
    rlPhaseEnd

    rlPhaseStartTest "Leftover process holding stderr only"
        run_test /test/stderr 0
        rlAssertGrep "^done$" "$(test_output stderr)"
        rlAssertGrep "$WARNING" "$(test_output stderr)" -F
    rlPhaseEnd

    rlPhaseStartTest "No leftover process"
        run_test /test/clean 0
        rlAssertNotGrep "tmt: warning" "$(test_output clean)"
    rlPhaseEnd

    rlPhaseStartTest "Daemon with redirected output"
        run_test /test/daemon 0
        rlAssertNotGrep "tmt: warning" "$(test_output daemon)"
        # Processes on the local guest are visible here
        if [ "$PROVISION_HOW" = "local" ]; then
            rlRun "pgrep -f '^sleep 4004$'" 0 "Daemon is still running"
        fi
    rlPhaseEnd

    # With tty, the test output goes straight to the pseudo-terminal of
    # the ssh session, and the end of the session sends the leftovers
    # SIGHUP. Local and container guests have no such terminal.
    if [ "$PROVISION_HOW" = "virtual" ]; then
        rlPhaseStartTest "Leftover process in a test with tty"
            run_test /test/tty 0
            rlAssertNotGrep "tmt: warning" "$(test_output tty)"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "pkill -f '^sleep 400[0-9]$'" 0,1 "Stop any leftover process"
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
