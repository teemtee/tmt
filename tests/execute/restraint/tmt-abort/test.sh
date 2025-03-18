#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"

        build_container_image "fedora/rawhide\:latest"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run -vvv --id \${run}" 2 "Expect error from execution to tmt-abort."
        # 2 tests discovered but only one is executed due to abort
        rlAssertGrep "1 test executed" $rlRun_LOG
        rlAssertGrep "total: 1 error and 2 pending" $rlRun_LOG

        rlAssertGrep "errr /default-0/abort" $rlRun_LOG
        rlAssertGrep "pending /default-0/do-not-run/1" $rlRun_LOG
        rlAssertGrep "pending /default-1/do-not-run/2" $rlRun_LOG

        rlAssertNotGrep "This test should not be executed." $rlRun_LOG
        rlAssertNotGrep "This should not be executed either." $rlRun_LOG
        rlAssertNotGrep "And neither should this." $rlRun_LOG

        rlAssertGrep "result: error" "${run}/plan/execute/results.yaml"
        rlAssertEquals "check expected outcomes" \
            "$(yq -r '[sort_by(.name) | .[] | "\(.name):\(.result)"] | join(" ")' ${run}/plan/execute/results.yaml)" \
            "/default-0/abort:error /default-0/do-not-run/1:pending /default-1/do-not-run/2:pending"
        rlAssertEquals "results should record the test aborted" \
            "$(yq -r '.[] | .note | join(", ")' ${run}/plan/execute/results.yaml)" \
            "beakerlib: State 'started', aborted"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
