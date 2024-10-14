#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'pushd data'
        rlRun 'set -o pipefail'
    rlPhaseEnd

    run="tmt --feeling-safe run"
    good="plan --name /plan/good"

    rlPhaseStartTest "Check environment-file option reads properly"
        rlRun -s "$run -rvvvddd $good"
        rlAssertGrep "total: 1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check if --environment overwrites --environment-file"
        rlRun "$run --environment STR=bad_str -rvvvddd $good 2>&1 \
            | tee output" 1
        rlAssertGrep "AssertionError: assert 'bad_str' == 'O'" 'output'
    rlPhaseEnd

    rlPhaseStartTest "Check if cli environment-file overwrites fmf"
        rlRun "$run --environment-file env-via-cli -rvvvddd $good 2>&1 \
            | tee output" 1
        rlAssertGrep "AssertionError: assert '2' == '1'" 'output'
    rlPhaseEnd

    rlPhaseStartTest "Bad dotenv format"
        rlRun -s "$run -rvvvddd plan -n bad" 2
        rlAssertGrep "Failed to extract variables from 'dotenv' format." $rlRun_LOG
        rlAssertGrep "not enough values to unpack (expected 2, got 1)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Empty environment file"
        rlRun "$run -rvvddd discover finish plan -n empty 2>&1 | tee output"
        rlAssertGrep "warn: Empty environment file" "output"
    rlPhaseEnd

    rlPhaseStartTest "Escape from the tree"
        rlRun -s "$run -rvvvddd plan -n escape" 2
        rlAssertGrep "Failed to extract variables from file '/etc/secret' as it lies outside the metadata tree root '$(pwd)'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Fetch a remote file"
        # Good
        rlRun -s "tmt plan show fetch/good"
        rlAssertGrep "STR: O" $rlRun_LOG
        rlAssertGrep "INT: 0"  $rlRun_LOG
        # Bad
        rlRun -s "tmt plan show fetch/bad" 2
        rlAssertGrep "Failed to extract variables from URL '.*/tests/core/env/data/wrong.yaml'."  $rlRun_LOG -E
        rlAssertGrep "404 Client Error: Not Found for url: .*/tests/core/env/data/wrong.yaml" $rlRun_LOG -E
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'rm output'
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
