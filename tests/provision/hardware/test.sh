#!/bin/bash
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

    rlPhaseStartTest "Check early exit on data size validation errors"
        rlRun -s "tmt run plan --name /plan/invalid-data-size" 2 "TMT should exit early on invalid data size"

        # Verify that TMT exits early and doesn't enter discover phase
        rlAssertNotGrep "discover" $rlRun_LOG
        rlAssertNotGrep "how: shell" $rlRun_LOG

        # Verify that the validation error is reported
        rlAssertGrep "Invalid unit: expected a data size unit" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check various input methods for hardware key"
        # Just the fmf input that's already in the plan
        rlRun -s "tmt -vv run --id $run --dry provision plan --name '^/plan/$PROVISION_HOW\$'"
        rlAssertGrep "method: bios" $rlRun_LOG

        # Invalid input, key=val no longer supported
        rlRun -s "tmt -vv run --id $run --dry provision --how $PROVISION_HOW --hardware hostname=bar.redhat.com plan --name '^/plan/$PROVISION_HOW\$'" 2

        # JSON blob via command line
        rlRun -s "tmt -vv run --id $run --dry provision --how $PROVISION_HOW --hardware '{\"hostname\": \"bar.redhat.com\"}' plan --name '^/plan/$PROVISION_HOW\$'"
        rlAssertGrep "hostname: bar.redhat.com" $rlRun_LOG

        # JSON blob from a file
        rlRun -s "tmt -vv run --id $run --dry provision --how $PROVISION_HOW --hardware @$(pwd)/hardware.json plan --name '^/plan/$PROVISION_HOW\$'"
        rlAssertGrep "hostname: baz.redhat.com" $rlRun_LOG

        # YAML blob from a file
        rlRun -s "tmt -vv run --id $run --dry provision --how $PROVISION_HOW --hardware @$(pwd)/hardware.yaml plan --name '^/plan/$PROVISION_HOW\$'"
        rlAssertGrep "hostname: quux.redhat.com" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
