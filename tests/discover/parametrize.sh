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
    plan_combined='plan -n parametrize/combined'
    plan_conflict='plan -n parametrize/conflict'
    plan_testselect='plan -n parametrize/testselect'
    steps='discover finish'

    rlPhaseStartTest 'From environment attribute'
        rlRun "tmt run -r $plan_env $steps 2>&1 >/dev/null | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'From --environment command line option'
        rlRun "tmt run -r -e REPO=tmt $plan_noenv $steps 2>&1 >/dev/null | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
        # Precedence of option over environment attribute
        rlRun "tmt run -r -e REPO=fmf $plan_env $steps 2>&1 >/dev/null | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/fmf' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Process environment should be ignored'
        rlRun "REPO=fmf tmt run -r $plan_env $steps 2>&1 >/dev/null | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
        # No substitution should happen
        rlRun "REPO=tmt tmt run -r $plan_noenv $steps 2>&1 >/dev/null | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/${REPO}' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Undefined variable'
        rlRun "tmt run -r $plan_noenv $steps 2>&1 >/dev/null | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/${REPO}' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'From context attribute'
        rlRun "tmt run -r $plan_ctx $steps 2>&1 >/dev/null | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'From --context command line option'
        rlRun "tmt -c repo=tmt run -r $plan_noctx $steps 2>&1 >/dev/null | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/tmt' 'output'
        # Precedence of option over context attribute
        rlRun "tmt -c repo=fmf run -r $plan_ctx $steps 2>&1 >/dev/null | tee output"
        rlAssertGrep 'url: https://github.com/teemtee/fmf' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Undefined context'
        rlRun "tmt run -r $plan_noctx $steps 2>&1 >/dev/null | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/$@{repo}' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Combined variable and context defined in a plan'
        rlRun "tmt run -r $plan_combined $steps 2>&1 >/dev/null | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/teemtee' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Combined variable and context defined on a cmdline'
        rlRun "tmt -c prefix=foo run --environment SUFFIX=bar -r $plan_combined $steps 2>&1 >/dev/null | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/foobar' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Using identical name for variable and context'
        rlRun "tmt run -r $plan_conflict $steps 2>&1 >/dev/null | tee output" 2
        rlAssertGrep 'url: https://github.com/teemtee/foobar' 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Empty context value should fail gracefully'
        rlRun "tmt -c foo= run -r $plan_noctx $steps 2>&1 | tee output" 2
        rlAssertGrep "Context dimension 'foo' has an empty value" 'output'
        rlAssertGrep "Use 'KEY=VALUE' format or remove the dimension entirely" 'output'
    rlPhaseEnd

    rlPhaseStartTest 'Using context and variable to select tests'
        rlRun -s "tmt -c PICK_FMF='^/tests/(unit|basic/ls)$' \
            run -e PICK_TMT='^/tests/core/ls$' \
             -r $plan_testselect discover -v finish > /dev/null"

        rlAssertGrep "tests: ^/tests/core/ls$" "$rlRun_LOG" -F
        rlAssertGrep "tests: ^/tests/(unit|basic/ls)$" "$rlRun_LOG" -F
        rlAssertGrep " 3 tests selected" "$rlRun_LOG" -F
        rlAssertGrep "/TMT/tests/core/ls" "$rlRun_LOG" -F
        rlAssertGrep "/FMF/tests/basic/ls" "$rlRun_LOG" -F
        rlAssertGrep "/FMF/tests/unit" "$rlRun_LOG" -F

    rlPhaseStartCleanup
        rlRun 'rm -f output' 0 'Removing tmp file'
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
