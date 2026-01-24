#!/bin/bash
# TEST-NAME: Edge case - test mode with --step discover (override)
# ====================
#
# WHAT THIS TESTS:
#   Tests that explicit --step discover overrides the implicit test mode
#   behavior, but results in an error because no guests exist during discover.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step discover -c true
#
# EXPECTED BEHAVIOR:
#   - The command should fail with exit code 1 or 2
#   - Error message should indicate "No guests ready for login"
#   - The explicit --step discover overrides the -t flag's default execute step
#
# KEY POINT:
#   Explicit --step discover should override the implicit --step execute
#   that -t normally provides, but discover is not a valid step for login
#   since guests don't exist yet.
#
# TEST DATA:
#   - Creates one normal passing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-10

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step discover (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step discover -c true" 0-2
        rlAssertGrep "No guests ready for login" "$rlRun_LOG" 0 "No guests in discover"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
