#!/bin/bash
# TEST-NAME: Test mode with --step provision (override)
# ====================
#
# WHAT THIS TESTS:
#   Tests that explicit --step provision overrides the implicit test mode
#   behavior, but results in an error because guests aren't ready during provision.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step provision -c true
#
# EXPECTED BEHAVIOR:
#   - The command should fail with exit code 1 or 2
#   - Error message should indicate "No guests ready for login"
#   - The explicit --step provision overrides the -t flag's default execute step
#
# KEY POINT:
#   Explicit --step provision should override the implicit --step execute
#   that -t normally provides, but provision is not a valid step for login
#   since guests aren't ready yet.
#
# TEST DATA:
#   - Creates two normal passing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section T-09

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step provision (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step provision -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
