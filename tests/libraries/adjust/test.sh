#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Matching context applies library adjust"
        rlRun "tmt --context distro=fedora-something run --id $run/matching --scratch discover"
        rlAssertGrep "coreutils$" "$run/matching/plan/discover/tests.yaml"
        rlAssertGrep "coreutils-debuginfo" "$run/matching/plan/discover/tests.yaml" -F
    rlPhaseEnd

    rlPhaseStartTest "Non-matching context keeps library require unchanged"
        rlRun "tmt --context distro=rhel-9 run --id $run/other --scratch discover"
        rlAssertGrep "coreutils$" "$run/other/plan/discover/tests.yaml"
        rlAssertNotGrep "coreutils-debuginfo" "$run/other/plan/discover/tests.yaml" -F
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove temporary directories"
    rlPhaseEnd
rlJournalEnd
