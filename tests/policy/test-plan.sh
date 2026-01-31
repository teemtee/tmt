#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data/plan"
    rlPhaseEnd

    rlPhaseStartTest "Sanity"
        # Not doing anything complex, test-level policy test covers plenty
        # of cases. Focusing on plan-specific modifications only.
        rlRun -s "tmt -vv plan export --policy-file ../../policies/plan/plan.yaml"
        rlAssertGrep "Apply tmt policy '../../policies/plan/plan.yaml' to plans." $rlRun_LOG

        rlRun -s "tmt -vv plan export --policy-file ../../policies/plan/plan.yaml 2> /dev/null"

        rlAssertEquals \
            "Verify that discover key is empty" \
            "$(yq -o json '.[] | .discover' $rlRun_LOG | jq -cSr)" \
            "null"
        rlAssertEquals \
            "Verify that prepare step contains two phases" \
            "$(yq -o json '.[] | .prepare | .[] | "\(.how):\(.order)"' $rlRun_LOG | jq -cSr)" \
            "feature:17
shell:null"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
