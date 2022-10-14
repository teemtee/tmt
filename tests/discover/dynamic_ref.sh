#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'pushd data'
        rlRun 'set -o pipefail'
    rlPhaseEnd

    plan_noctx='plan -n dynamic_ref_noctx'
    plan_ctx='plan -n dynamic_ref_ctx'
    plan_env='plan -n dynamic_ref_env'
    steps='discover finish'

    rlPhaseStartTest 'Check dynamic ref without "branch" context'
        rlRun "tmt run -r $plan_noctx $steps | tee output" 0,2
        rlAssertGrep 'ref: tmt' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Check dynamic ref with "branch=fmf"'
        rlRun "tmt -c branch=fmf run -r $plan_noctx $steps | tee output" 0,2
        rlAssertGrep 'ref: fmf' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Check dynamic ref with "branch=fmf" defined in a test plan'
        rlRun "tmt run -r $plan_ctx $steps | tee output" 0,2
        rlAssertGrep 'ref: fmf' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Check dynamic ref with context override through --context"'
        rlRun "tmt -c branch=tmt run -r $plan_ctx $steps | tee output" 0,2
        rlAssertGrep 'ref: tmt' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'REF defined through --environment should not impact dynamic ref'
        rlRun "tmt run --environment REF=fmf -r $plan_noctx $steps | tee output" 0,2
        rlAssertGrep 'ref: tmt' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'REF defined in a test plan should not impact dynamic ref'
        rlRun "tmt run -r $plan_env $steps | tee output" 0,2
        rlAssertGrep 'ref: tmt' 'output'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'rm -f output' 0 'Removing tmp file'
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
