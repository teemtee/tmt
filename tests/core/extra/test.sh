#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    # C000 = key "..." not recognized by schema
    base_args=(--enable-check C000 --enforce-check C000)

    rlPhaseStartTest "Test metadata"
        # T001 = unknown key "..." is used (in a test)
        args=("${base_args[@]}" --enable-check T001 --enforce-check T001)
        rlRun 'tmt lint "${args[@]}" /valid-test$' 0
        rlRun 'tmt lint "${args[@]}" /valid-test-mapping$' 0
        rlRun 'tmt lint "${args[@]}" /valid-test-sequence$' 0
        rlRun 'tmt lint "${args[@]}" /invalid-test$' 1
    rlPhaseEnd

    rlPhaseStartTest "Plan metadata"
        # P001 = unknown key "..." is used (in a plan)
        args=("${base_args[@]}" --enable-check P001 --enforce-check P001)
        rlRun 'tmt lint "${args[@]}" /valid-plan$' 0
        rlRun 'tmt lint "${args[@]}" /invalid-plan$' 1
    rlPhaseEnd

    rlPhaseStartTest "Story metadata"
        # S001 = unknown key "..." is used (in a story)
        args=("${base_args[@]}" --enable-check S001 --enforce-check S001)
        rlRun 'tmt lint "${args[@]}" /valid-story$' 0
        rlRun 'tmt lint "${args[@]}" /invalid-story$' 1
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
