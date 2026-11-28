#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "workdir=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun 'pushd data'
    rlPhaseEnd

    plan='plan --name /tests'

    rlPhaseStartTest
        rlRun -s "tmt run --id $workdir -vvv  $plan"
        rlAssertGrep "package: 1 package requested" "$rlRun_LOG" -F
        rlAssertGrep "test: Concise summary" "$rlRun_LOG" -F
        rlAssertGrep '00:00:00 pass /first (on default-0) [1/2]' "$rlRun_LOG" -F
        rlAssertGrep "Note: test failed as expected" $rlRun_LOG
        rlAssertGrep "Note: original test result: fail" $rlRun_LOG
        rlAssertGrep '00:00:00 pass /second (on default-0) [2/2]' "$rlRun_LOG" -F
    rlPhaseEnd

    rlPhaseStartTest "Attribute 'adjust' is applied"
        rlRun -s "tmt -c some_dimension=1 run --scratch --id $workdir -vvv $plan"
        rlAssertGrep "summary: 1 test selected" "$rlRun_LOG" -F
        rlAssertNotGrep "/first (on default-0)" "$rlRun_LOG" -F
        rlAssertGrep '00:00:00 pass /second (on default-0) [1/1]' "$rlRun_LOG" -F
    rlPhaseEnd

    # Attributes 'tier', 'link', 'tag', 'component' are not usable for filtering
    # 'require' and 'recommend' doesn't accept fmf-id dictionary

    rlPhaseStartCleanup
        rlRun 'popd'
        rlRun "rm -rf $workdir" 0 'Remove tmp directory'
    rlPhaseEnd
rlJournalEnd
