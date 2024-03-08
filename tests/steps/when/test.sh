#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1


rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd


    rlPhaseStartTest
        # No tests discovered
        rlRun -s "tmt run --id $tmp/no-context" "3"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt -c distro=fedora -c trigger=commit run --id $tmp/distro-trigger-context"
        rlAssertExists "$tmp/distro-trigger-context/plan/data/when-in-discover"
        rlAssertExists "$tmp/distro-trigger-context/plan/data/when-prepare-always"
        rlAssertExists "$tmp/distro-trigger-context/plan/data/when-prepare-fedora"
        rlAssertExists "$tmp/distro-trigger-context/plan/data/when-report-fedora"
        rlAssertNotExists "$tmp/distro-trigger-context/plan/data/when-finish-no-distro"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt -c trigger=commit run --id $tmp/trigger-context"
        rlAssertExists "$tmp/trigger-context/plan/data/when-in-discover"
        rlAssertExists "$tmp/trigger-context/plan/data/when-prepare-always"
        rlAssertNotExists "$tmp/trigger-context/plan/data/when-prepare-fedora"
        rlAssertNotExists "$tmp/trigger-context/plan/data/when-report-fedora"
        rlAssertExists "$tmp/trigger-context/plan/data/when-finish-no-distro"
    rlPhaseEnd


    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
