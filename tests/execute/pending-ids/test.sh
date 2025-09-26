#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
    rlPhaseEnd

    rlPhaseStartTest "Every test must have ids available when host becomes unresponsive (#3784)."
        rlRun -s "tmt run -vv -a -i $run provision -h $PROVISION_HOW" 2
        rlAssertGrep 'pass /test/1-passed' $rlRun_LOG '-F'
        rlAssertGrep 'errr /test/2-error' $rlRun_LOG '-F'
        rlAssertGrep 'pending /test/3-pending' $rlRun_LOG '-F'
        rlAssertGrep 'pending /test/4-no-id-pending' $rlRun_LOG '-F'

        rlAssertGrep '86ef8a3d-bb6c-4c6e-86bb-1751ab8da302' ${run}/plan/execute/results.yaml
        rlAssertGrep '2af20892-8474-4cf9-ba8c-b9bd1cca5078' ${run}/plan/execute/results.yaml
        rlAssertGrep '5435a332-3b68-4bd4-a614-ac5b605ae346' ${run}/plan/execute/results.yaml
        rlAssertGrep 'TC#0118999' ${run}/plan/execute/results.yaml
        rlAssertGrep '/fire/!/fire' ${run}/plan/execute/results.yaml
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
