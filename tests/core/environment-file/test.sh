#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=$(mktemp -d)"
        rlRun 'pushd data'
        rlRun 'set -o pipefail'
    rlPhaseEnd

    good="plan --name /plan/good"
    tmt="tmt run --id $run --scratch -vvvddd"

    rlPhaseStartTest "Check environment-file option reads properly"
        rlRun "$tmt $good | tee output"
        rlAssertGrep "total: 1 test passed" 'output'
    rlPhaseEnd

    rlPhaseStartTest "Check if --environment overwrites --environment-file"
        rlRun "$tmt --environment STR=bad_str $good 2>&1 \
            | tee output" 1
        rlAssertGrep "AssertionError: assert 'bad_str' == 'O'" 'output'
    rlPhaseEnd

    rlPhaseStartTest "Check if cli environment-file overwrites fmf"
        rlRun "$tmt --environment-file env-via-cli $good 2>&1 \
            | tee output" 1
        rlAssertGrep "AssertionError: assert '2' == '1'" 'output'
    rlPhaseEnd

    rlPhaseStartTest "Bad dotenv format"
        rlRun "$tmt plan -n bad 2>&1 | tee output" 2
        rlAssertGrep "Failed to extract variables.*data/bad" 'output'
    rlPhaseEnd

    rlPhaseStartTest "Empty environment file"
        rlRun "$tmt discover plan -n empty 2>&1 | tee output"
        rlAssertGrep "environment: {}" "output"
        rlAssertGrep "WARNING.*Empty environment file" "output"
    rlPhaseEnd

    rlPhaseStartTest "Escape from the tree"
        rlRun "$tmt plan -n escape 2>&1 | tee output" 2
        rlAssertGrep "path '/etc/secret' is outside" 'output'
    rlPhaseEnd

    rlPhaseStartTest "Fetch a remote file"
        # Good
        rlRun "tmt plan show fetch/good | tee output"
        rlAssertGrep "STR: O" 'output'
        rlAssertGrep "INT: 0" 'output'
        # Bad
        rlRun "tmt plan show fetch/bad 2>&1 | tee output" 2
        rlAssertGrep "Failed to fetch the environment file" 'output'
        rlAssertGrep "Name or service not known" 'output'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf output $run"
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
