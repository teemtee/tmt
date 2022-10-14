#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'pushd data'
        rlRun 'set -o pipefail'
    rlPhaseEnd

    plan_noenv='plan -n parametrize/noenvironment'
    plan_env='plan -n parametrize/environment'
    plan_noctx='plan -n parametrize/nocontext'
    plan_ctx='plan -n parametrize/context'
    steps='discover finish'

    rlPhaseStartTest 'From environment attribute'
        rlRun "tmt run -r $plan_env $steps | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'From --environment command line option'
        rlRun "tmt run -r -e REPO=tmt $plan_noenv $steps | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
        # Precedence of option over environment attribute
        rlRun "tmt run -r -e REPO=fmf $plan_env $steps | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/fmf' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Process environment should be ignored'
        rlRun "REPO=fmf tmt run -r $plan_env $steps | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
        # No substitution should happen
        rlRun "REPO=tmt tmt run -r $plan_noenv $steps | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/${REPO}' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Undefined variable'
        rlRun "tmt run -r $plan_noenv $steps | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/${REPO}' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'From context attribute'
        rlRun "tmt run -r $plan_ctx $steps | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'From --context command line option'
        rlRun "tmt -c repo=tmt run -r $plan_noctx $steps | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
        # Precedence of option over context attribute
        rlRun "tmt -c repo=fmf run -r $plan_ctx $steps | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/fmf' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Undefined context'
        rlRun "tmt run -r $plan_noctx $steps | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/${repo}' 'output'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'rm -f output' 0 'Removing tmp file'
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
