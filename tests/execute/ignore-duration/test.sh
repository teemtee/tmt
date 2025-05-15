#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1


rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "export TMT_WORKDIR_ROOT=$tmp"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "No envvar used"
        rlRun -s "tmt run -vv plan -n /no-option" "2"
        rlAssertGrep 'errr /demo/test' $rlRun_LOG '-F'
        rlAssertGrep 'Note: timeout' $rlRun_LOG '-F'

        rlRun "tmt run -vv plan -n /via-plan-true" "0"

        rlRun "tmt run -vv plan -n /via-plan-false" "2"
        rlAssertGrep 'errr /demo/test' $rlRun_LOG '-F'
        rlAssertGrep 'Note: timeout' $rlRun_LOG '-F'
    rlPhaseEnd

    rlPhaseStartTest "With IGNORE_DURATION=1"
        export TMT_PLUGIN_EXECUTE_TMT_IGNORE_DURATION=1
        rlRun "tmt run -vv plan -n /no-option"
        rlRun "tmt run -vv plan -n /via-plan-true"
        # ENV should win over CLI or file values, but to be consistent with
        # reporportal/polarion plugin envar is weaker than plan.fmf
        rlRun "tmt run -vv plan -n /via-plan-false" "2"
    rlPhaseEnd

    rlPhaseStartTest "With IGNORE_DURATION=0"
        export TMT_PLUGIN_EXECUTE_TMT_IGNORE_DURATION=0
        rlRun "tmt run -vv plan -n /no-option" "2"
        # ENV should win over CLI or file values, but to be consistent with
        # reporportal/polarion plugin envar is weaker than plan.fmf
        rlRun "tmt run -vv plan -n /via-plan-true"
        rlRun "tmt run -vv plan -n /via-plan-false" "2"
    rlPhaseEnd


    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
