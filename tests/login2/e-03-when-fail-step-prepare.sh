#!/bin/bash
# TEST-NAME: Edge case - --when with --step prepare
# ====================
#
# WHAT THIS TESTS:
#   Tests the edge case of combining conditional login (--when fail) with
#   a step before execute (--step prepare), where test results don't exist yet.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail --step prepare -c true
#
# EXPECTED BEHAVIOR:
#   - Behavior is undefined for --when with steps before execute
#   - The test documents actual behavior (may change or error)
#   - This is a future-looking scenario (prepare before results are known)
#
# KEY POINT:
#   This is an edge case because --when conditions depend on test results,
#   but prepare step occurs before tests execute. The behavior is
#   intentionally undefined/documented for future consideration.
#
# TEST DATA:
#   - Creates one failing test (prepare step is explicitly enabled)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-03

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan true
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --step prepare (edge case)"
        # This is an edge case - --when with a step before execute
        # The behavior is undefined/should be no login
        rlRun -s "tmt run -ar provision -h container login --when fail --step prepare -c true" 0-2
        # Document the actual behavior for now
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
