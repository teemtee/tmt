#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
    rlPhaseEnd

    rlPhaseStartTest "Check $PROVISION_HOW plugin"
        rlRun -s "tmt -vv plan show /plan/$PROVISION_HOW"

        rlAssertNotGrep "warn: " $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check and/or combinations with other constraints (https://github.com/teemtee/tmt/issues/3273)"
        rlRun -s "tmt -vv plan show /plan/and-does-not-combine"
        rlAssertGrep "is not valid under any of the given schemas" $rlRun_LOG

        rlRun -s "tmt -vv plan show /plan/or-does-not-combine"
        rlAssertGrep "is not valid under any of the given schemas" $rlRun_LOG

        rlRun -s "tmt plan lint --enable-check C000 --enforce-check C000 '^/plan/and-does-not-combine'" 1
        rlAssertGrep "warn -> fail C000 fmf node failed schema validation" $rlRun_LOG

        rlRun -s "tmt plan lint --enable-check C000 --enforce-check C000 '^/plan/and-does-not-combine'" 1
        rlAssertGrep "warn -> fail C000 fmf node failed schema validation" $rlRun_LOG

        rlRun -s "tmt plan lint --enable-check C000 --enforce-check C000 '^/plan/and-or-safe'" 0
        rlAssertNotGrep "warn -> fail C000 fmf node failed schema validation" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
