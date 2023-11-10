#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Logging topics"
        rlRun -s "tmt -dddd plan show /plans/features/core > /dev/null"
        rlAssertNotGrep "key source" $rlRun_LOG
        rlAssertNotGrep "normalized fields" $rlRun_LOG

        rlRun -s "tmt --log-topic=key-normalization -dddd plan show /plans/features/core > /dev/null"
        rlAssertGrep "key source" $rlRun_LOG
        rlAssertGrep "normalized fields" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Timestamps on terminal"
        rlRun -s "tmt             -dd plan show /plans/features/core > /dev/null"
        rlRun "grep -E '^[[:digit:]]{2}:[[:digit:]]{2}:[[:digit:]]{2} ' $rlRun_LOG" 1

        rlRun -s "tmt --show-time -dd plan show /plans/features/core > /dev/null"
        rlRun "grep -E '^[[:digit:]]{2}:[[:digit:]]{2}:[[:digit:]]{2} ' $rlRun_LOG" 0
    rlPhaseEnd

    # TODO: enable the test once --quiet starts silencing all kinds of logging
    # See https://github.com/teemtee/tmt/issues/2106
    # rlPhaseStartTest "Verify --quiet suppresses all logging"
    #     rlRun "pushd data"
    #
    #     rlRun -s "tmt test show"
    #     rlAssertGrep "warn: /tests: - 'non-existent-key' does not match any of the regexes" "$rlRun_LOG"
    #
    #     rlRun -s "tmt --quiet test show"
    #     rlAssertNotGrep "warn: /tests: - 'non-existent-key' does not match any of the regexes" "$rlRun_LOG"
    #
    #     rlRun "popd"
    # rlPhaseEnd

    rlPhaseStartCleanup
    rlPhaseEnd
rlJournalEnd
