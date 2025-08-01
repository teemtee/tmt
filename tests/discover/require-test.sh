#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "workdir=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'pushd require-test'
    rlPhaseEnd

    rlPhaseStartTest "All tests are required and should be discovered"
        rlRun -s "tmt run --id $workdir --scratch -vvv discover plan -n /plans/good"
        rlAssertGrep "summary: 4 tests selected" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Some required tests are not discovered (fmf)"
        rlRun -s "tmt run --id $workdir --scratch -vvv discover plan -n /plans/bad/fmf" 2
        rlAssertGrep "Required test '/tests/fail' not discovered" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Some required tests are not discovered (shell)"
        rlRun -s "tmt run --id $workdir --scratch -vvv discover plan -n /plans/bad/shell" 2
        rlAssertGrep "Required test '/tests/shell-fail' not discovered" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'popd'
        rlRun "rm -rf $workdir" 0 'Remove tmp directory'
    rlPhaseEnd
rlJournalEnd
