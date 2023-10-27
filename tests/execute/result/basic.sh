#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

run()
{
    res=$1  # expected final result of test
    tn=$2   # test name
    orig=$3 # original result
    ret=$4  # tmt return code

    rlRun -s "tmt run -a --scratch --id \${run} test --name ${tn} provision --how local report -v 2>&1 >/dev/null | grep report -A2 | tail -n 1" \
        ${ret} "Result: ${res}, Test name: ${tn}, Original result: '${orig}', tmt return code: ${ret}"

    if [ -z "${orig}" ]; then # No original result provided
        rlAssertGrep "${res} ${tn}$" $rlRun_LOG
    else
        rlAssertGrep "${res} ${tn} (original result: ${orig})$" $rlRun_LOG
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
        #     result    test name            original  return
        #                                     result    code
        run   "pass"   "/test/pass"           ""         0
        run   "fail"   "/test/fail"           ""         1
        run   "errr"   "/test/error"          ""         2
        run   "pass"   "/test/xfail-fail"     "fail"     0
        run   "fail"   "/test/xfail-pass"     "pass"     1
        run   "errr"   "/test/xfail-error"    "error"    2
        run   "pass"   "/test/always-pass"    "fail"     0
        run   "info"   "/test/always-info"    "pass"     0
        run   "warn"   "/test/always-warn"    "pass"     1
        run   "fail"   "/test/always-fail"    "pass"     1
        run   "errr"   "/test/always-error"   "pass"     2
    rlPhaseEnd

    rlPhaseStartTest "Verbose execute prints result"
        rlRun -s "tmt run --id \${run} --scratch --until execute tests --filter tag:-cherry_pick provision --how local execute -v 2>&1 >/dev/null" "2"
        while read -r line; do
            if rlIsRHELLike "=8" && [[ $line =~ /test/error-timeout ]]; then
                # Centos stream 8 doesn't do watchdog properly https://github.com/teemtee/tmt/issues/1387
                # so we can't assert expected duration (1s) in /test/error-timeout
                # FIXME remove this once issue is fixed
                rlAssertGrep "errr /test/error-timeout (on default-0) (timeout) [7/12]" "$rlRun_LOG" -F
            else
                rlAssertGrep "$line" "$rlRun_LOG" -F
            fi
        done <<-EOF
00:00:00 errr /test/always-error (on default-0) (original result: pass) [1/12]
00:00:00 fail /test/always-fail (on default-0) (original result: pass) [2/12]
00:00:00 info /test/always-info (on default-0) (original result: pass) [3/12]
00:00:00 pass /test/always-pass (on default-0) (original result: fail) [4/12]
00:00:00 warn /test/always-warn (on default-0) (original result: pass) [5/12]
00:00:00 errr /test/error (on default-0) [6/12]
00:00:01 errr /test/error-timeout (on default-0) (timeout) [7/12]
00:00:00 fail /test/fail (on default-0) [8/12]
00:00:00 pass /test/pass (on default-0) [9/12]
00:00:00 errr /test/xfail-error (on default-0) (original result: error) [10/12]
00:00:00 pass /test/xfail-fail (on default-0) (original result: fail) [11/12]
00:00:00 fail /test/xfail-pass (on default-0) (original result: pass) [12/12]
EOF
    rlPhaseEnd

    rlPhaseStartTest "Verbose execute prints result - reboot case"
        # Before the reboot results is not known
        rlRun -s "tmt run --id \${run} --scratch --until execute tests -n /xfail-with-reboot provision --how container execute -v 2>&1 >/dev/null"
        EXPECTED=$(cat <<EOF
            00:00:00 /test/xfail-with-reboot [1/1]
            00:00:00 pass /test/xfail-with-reboot (on default-0) (original result: fail) [1/1]
EOF
)
    rlAssertEquals "Output matches the expectation" "$EXPECTED" "$(grep /test/xfail-with-reboot $rlRun_LOG)"
    rlPhaseEnd

    rlPhaseStartTest "Verbose execute prints result - abort case"
        rlRun -s "tmt run --id \${run} --scratch --until execute tests -n /abort provision --how container execute -v 2>&1 >/dev/null" "2"
        rlAssertGrep "00:00:00 errr /test/abort (on default-0) (aborted) [1/1" $rlRun_LOG -F
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
