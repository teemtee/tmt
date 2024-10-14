#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd data"
    rlPhaseEnd

    for execute_method in tmt; do
        for tty in "tty on default" "tty requested"; do
            for interactive in "" "--interactive"; do
                if [ "$tty" = "tty requested" ]; then
                    context="-c tty=true"
                else
                    context=""
                fi

                rlPhaseStartTest "Test provision $PROVISION_HOW, execute $execute_method, $tty, $interactive short tests"
                    rlRun -s "tmt $context --log-topic=command-events run --scratch -vfi $tmp -a provision -h $PROVISION_HOW execute -h $execute_method $interactive test --name short" 0

                    rlRun "grep 'duration \"5\" exceeded' $tmp/log.txt" 1
                rlPhaseEnd

                rlPhaseStartTest "Test provision $PROVISION_HOW, execute $execute_method, $tty, $interactive long tests"
                    if [ "$interactive" = "" ]; then
                        rlRun -s "tmt $context --log-topic=command-events run --scratch -vfi $tmp -a provision -h $PROVISION_HOW execute -h $execute_method $interactive test --name long" 2

                        rlAssertNotGrep "warn: Ignoring requested duration, not supported in interactive mode." $rlRun_LOG
                    else
                        rlRun -s "tmt $context --log-topic=command-events run --scratch -vfi $tmp -a provision -h $PROVISION_HOW execute -h $execute_method $interactive test --name long" 0

                        rlAssertGrep "warn: Ignoring requested duration, not supported in interactive mode." $rlRun_LOG
                    fi

                    rlAssertNotGrep "00:02:.. errr /test/long/beakerlib (timeout)" $rlRun_LOG
                    rlAssertNotGrep "00:02:.. errr /test/long/shell (timeout)" $rlRun_LOG

                    if [ "$interactive" = "" ]; then
                        rlRun -s "tmt --log-topic=command-events run --last report -fvvvv" 2

                        rlAssertGrep "Maximum test time '5s' exceeded." $rlRun_LOG
                        rlAssertGrep "Adjust the test 'duration' attribute" $rlRun_LOG
                        rlAssertGrep "spec/tests.html#duration" $rlRun_LOG

                        rlRun -s "grep -A4 'duration \"5\" exceeded' $tmp/log.txt"

                        rlRun "grep -E ' [[:digit:]]{1,2}\.[[:digit:]]+ sent SIGKILL signal' $rlRun_LOG"
                        rlRun "grep -E ' [[:digit:]]{1,2}\.[[:digit:]]+ kill confirmed' $rlRun_LOG"
                        rlRun "grep -E ' [[:digit:]]{1,2}\.[[:digit:]]+ waiting for stream readers' $rlRun_LOG"
                        rlRun "grep -E ' [[:digit:]]{1,2}\.[[:digit:]]+ stdout reader done' $rlRun_LOG"
                    else
                        rlRun -s "tmt --log-topic=command-events run --last report -fvvvv" 0

                        rlAssertNotGrep "Maximum test time '5s' exceeded." $rlRun_LOG
                        rlAssertNotGrep "Adjust the test 'duration' attribute" $rlRun_LOG
                        rlAssertNotGrep "spec/tests.html#duration" $rlRun_LOG

                        rlAssertNotGrep "duration \"5\" exceeded" $tmp/log.txt

                        rlRun "grep -E ' [[:digit:]]{1,2}\.[[:digit:]]+ sent SIGKILL signal' $rlRun_LOG" 1
                        rlRun "grep -E ' [[:digit:]]{1,2}\.[[:digit:]]+ kill confirmed' $rlRun_LOG" 1
                        rlRun "grep -E ' [[:digit:]]{1,2}\.[[:digit:]]+ waiting for stream readers' $rlRun_LOG" 1
                        rlRun "grep -E ' [[:digit:]]{1,2}\.[[:digit:]]+ stdout reader done' $rlRun_LOG" 1
                    fi
                rlPhaseEnd
            done
        done
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
