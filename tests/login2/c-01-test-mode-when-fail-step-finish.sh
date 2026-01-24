#!/bin/bash
# C-01: Login -t --when fail --step finish
# =========================================
#
# WHAT THIS TESTS:
#   Combined test mode, conditional filter, and explicit step - additive behavior.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - `-t --when fail` provides per-test login after each failing test (in execute)
#   - `--step finish` adds an additional login in finish step
#   - Both behaviors COMBINE (additive)
#   - With pass + fail tests, should see 2 logins:
#     * 1 login after the failing test (in execute)
#     * 1 login in finish step
#
# KEY POINT:
#   `-t` always means per-test login in execute (filtered by --when).
#   Explicit `--step finish` adds another login in finish.
#   The `--when fail` condition applies to both steps.
#
# TEST DATA:
#   - pass test: exits with 0
#   - fail test: exits with 1
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "C-01 to C-10: Combined Scenarios"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
