#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data/plan"
    rlPhaseEnd

    rlPhaseStartTest "Export"
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
        rlAssertEquals \
            "Verify that contact key was populated" \
            "$(yq -o json '.[] | .contact | .[]' $rlRun_LOG | jq -cSr)" \
            "xyzzy"
    rlPhaseEnd

    rlPhaseStartTest "Run"
        # Not doing anything complex, just try to run a plan that should
        # be modified by a policy.
        rlRun -s "tmt -vv run -a --policy-file ../../policies/plan/simple.yaml" 3

        rlAssertGrep "Apply tmt policy '../../policies/plan/simple.yaml' to plans." $rlRun_LOG
        rlAssertGrep "No tests found, finishing plan." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
