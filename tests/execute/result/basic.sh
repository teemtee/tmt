#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

function test_result () {
    pattern="$1"
    extra_lines="$2"

    shift 2

    rlRun "grep -P -A$extra_lines \"\s+\d\d:\d\d:\d\d\s+$pattern\" $run/report.txt > $run/test.txt"
    rlRun "cat $run/test.txt"

    for i in `seq 1 $extra_lines`; do
        pattern="$1"
        shift

        rlRun "grep -P \"\s+$pattern\" $run/test.txt"
    done
}

run()
{
    res=$1  # expected final result of test
    tn=$2   # test name
    orig=$3 # original result
    ret=$4  # tmt return code

    if [ -z "${orig}" ]; then extra_lines=2; else extra_lines=3; fi

    rlRun -s "tmt run -a --scratch --id \${run} test --name ${tn} provision --how local report -v 2>&1 >/dev/null | grep report -A$extra_lines" \
        ${ret} "Result: ${res}, Test name: ${tn}, Original result: '${orig}', tmt return code: ${ret}"

    if [ -z "${orig}" ]; then # No original result provided
        rlAssertGrep "${res} ${tn}$" $rlRun_LOG
    else
        rlAssertGrep "${res} ${tn}$" $rlRun_LOG
        rlAssertGrep "Note: ${orig}" $rlRun_LOG
    fi

    echo
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd basic"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Running tests separately"
        ###   Table of expected results
        #
        #     result    test name            note                             return
        #                                                                      code
        run   "pass"   "/test/pass"           ""                                 0
        run   "fail"   "/test/fail"           ""                                 1
        run   "errr"   "/test/error"          ""                                 2
        run   "pass"   "/test/xfail-fail"     "test failed as expected"          0
        run   "fail"   "/test/xfail-pass"     "test was expected to fail"        1
        run   "errr"   "/test/xfail-error"    ""                                 2
        run   "pass"   "/test/always-pass"    "test result overridden: pass"     0
        run   "info"   "/test/always-info"    "test result overridden: info"     0
        run   "warn"   "/test/always-warn"    "test result overridden: warn"     1
        run   "fail"   "/test/always-fail"    "test result overridden: fail"     1
        run   "errr"   "/test/always-error"   "test result overridden: error"    2
    rlPhaseEnd

    rlPhaseStartTest "Verbose execute prints result"
        rlRun -s "tmt run --id \${run} --scratch --until execute tests --filter tag:-cherry_pick provision --how local execute -v 2>&1 >/dev/null" "2"
        rlRun "mv $rlRun_LOG $run/report.txt"

        test_result "errr /test/always-error \(on default-0\) \[1/12\]" \
                    2 \
                    "Note: test result overridden: error" \
                    "Note: original test result: pass"
        test_result "fail /test/always-fail \(on default-0\) \[2/12\]" \
                    2 \
                    "Note: test result overridden: fail" \
                    "Note: original test result: pass"
        test_result "info /test/always-info \(on default-0\) \[3/12\]" \
                    2 \
                    "Note: test result overridden: info" \
                    "Note: original test result: pass"
        test_result "pass /test/always-pass \(on default-0\) \[4/12\]" \
                    2 \
                    "Note: test result overridden: pass" \
                    "Note: original test result: fail"
        test_result "warn /test/always-warn \(on default-0\) \[5/12\]" \
                    2 \
                    "Note: test result overridden: warn" \
                    "Note: original test result: pass"
        test_result "errr /test/error \(on default-0\) \[6/12\]" \
                    0
        test_result "errr /test/error-timeout \(on default-0\) \[7/12\]" \
                    1 \
                    "Note: timeout"
        test_result "fail /test/fail \(on default-0\) \[8/12\]" \
                    0
        test_result "pass /test/pass \(on default-0\) \[9/12\]" \
                    0
        test_result "errr /test/xfail-error \(on default-0\) \[10/12\]" \
                    0
        test_result "pass /test/xfail-fail \(on default-0\) \[11/12\]" \
                    2 \
                    "Note: test failed as expected" \
                    "Note: original test result: fail"
        test_result "fail /test/xfail-pass \(on default-0\) \[12/12\]" \
                2 \
                "Note: test was expected to fail" \
                "Note: original test result: pass"
    rlPhaseEnd

    rlPhaseStartTest "Verbose execute prints result - reboot case"
        # Before the reboot results is not known
        rlRun -s "tmt run --id \${run} --scratch --until execute tests -n /xfail-with-reboot provision --how container execute -v 2>&1 >/dev/null"

        rlAssertGrep "00:00:00 /test/xfail-with-reboot \[1/1\]" $rlRun_LOG
        rlAssertGrep "00:00:00 pass /test/xfail-with-reboot (on default-0) \[1/1\]" $rlRun_LOG
        rlAssertGrep "Note: test failed as expected" $rlRun_LOG
        rlAssertGrep "Note: original test result: fail" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verbose execute prints result - abort case"
        rlRun -s "tmt run --id \${run} --scratch --until execute tests -n /abort provision --how container execute -v 2>&1 >/dev/null" "2"

        rlAssertGrep "00:00:00 errr /test/abort (on default-0) \[1/1\]" $rlRun_LOG
        rlAssertGrep "Note: aborted" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify fmf context lands in results"
        rlRun -s "tmt -c foo=bar run --id ${run} --scratch -a provision --how local test -n '/pass'"
        rlAssertEquals "Context is stored in result" "$(yq -r ".[] | .context | to_entries[] | \"\\(.key)=\\(.value[])\"" $run/default/plan/execute/results.yaml)" "foo=bar"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
