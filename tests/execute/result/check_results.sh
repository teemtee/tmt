#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

run()
{
    res=$1  # expected final result of test
    tn=$2   # test name
    ret=$3  # tmt return code

    rlRun -s "tmt run -a --scratch --id \${run} test --name ${tn} provision --how local report -v 2>&1 >/dev/null | grep report -A2 | tail -n 1" \
        ${ret} "Result: ${res}, Test name: ${tn}, tmt return code: ${ret}"

    rlAssertGrep "${res} ${tn}" $rlRun_LOG

    echo
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd check_results"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check Results Tests"
        run "pass" "/test/check-pass" 0
        run "fail" "/test/check-fail-respect" 1
        run "pass" "/test/check-fail-info" 0
        run "fail" "/test/check-xfail-pass" 1
        run "pass" "/test/check-xfail-fail" 0
        run "pass" "/test/check-override" 0
    rlPhaseEnd

    rlPhaseStartTest "Verbose execute prints result"
        rlRun -s "tmt run --id \${run} --scratch --until execute tests --filter tag:-cherry_pick provision --how local execute -v 2>&1 >/dev/null" "1"

        while read -r line; do
            rlAssertGrep "$line" "$rlRun_LOG" -F
        done <<-EOF
00:00:00 pass /test/check-fail-info (on default-0) [1/6]
00:00:00 fail /test/check-fail-respect (on default-0) (Check 'dmesg' failed, original result: pass) [2/6]
00:00:00 pass /test/check-override (on default-0) [3/6]
00:00:00 pass /test/check-pass (on default-0) [4/6]
00:00:00 pass /test/check-xfail-fail (on default-0) [5/6]
00:00:00 fail /test/check-xfail-pass (on default-0) (Check 'dmesg' failed, original result: pass) [6/6]
EOF
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
