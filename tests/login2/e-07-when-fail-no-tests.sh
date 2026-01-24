#!/bin/bash
# TEST-NAME: Edge case - --when fail with no tests
# ====================
#
# WHAT THIS TESTS:
#   Tests the edge case of conditional login (--when fail) when no tests
#   are discovered, which means there are no results to evaluate.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - No login should occur (no failed tests exist)
#   - The command may succeed or fail (documenting actual behavior)
#   - This tests handling of empty test result sets
#
# KEY POINT:
#   This tests the edge case where no tests are discovered. Without test
#   results, --when conditions cannot match, so no login should occur.
#
# TEST DATA:
#   - Creates a plan with no tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-07

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan_no_tests
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail with no tests discovered"
        rlRun -s "tmt run -ar provision -h container login --when fail -c true" 0-2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
