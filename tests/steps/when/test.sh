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
        rlRun -s "tmt run --id $tmp/no-context plan -n '/sanity'" "3"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt -c distro=fedora -c trigger=commit run --id $tmp/distro-trigger-context plan -n '/sanity'"
        rlAssertExists "$tmp/distro-trigger-context/plan/sanity/data/when-in-discover"
        rlAssertExists "$tmp/distro-trigger-context/plan/sanity/data/when-prepare-always"
        rlAssertExists "$tmp/distro-trigger-context/plan/sanity/data/when-prepare-fedora"
        rlAssertExists "$tmp/distro-trigger-context/plan/sanity/data/when-report-fedora"
        rlAssertNotExists "$tmp/distro-trigger-context/plan/sanity/data/when-finish-no-distro"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt -c trigger=commit run --id $tmp/trigger-context plan -n '/sanity'"
        rlAssertExists "$tmp/trigger-context/plan/sanity/data/when-in-discover"
        rlAssertExists "$tmp/trigger-context/plan/sanity/data/when-prepare-always"
        rlAssertNotExists "$tmp/trigger-context/plan/sanity/data/when-prepare-fedora"
        rlAssertNotExists "$tmp/trigger-context/plan/sanity/data/when-report-fedora"
        rlAssertExists "$tmp/trigger-context/plan/sanity/data/when-finish-no-distro"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run --id $tmp/execute-must-obey plan -n '/execute-must-obey'"
        rlAssertExists "$tmp/execute-must-obey/plan/execute-must-obey/execute/data/guest/default-0/shell-run"
        rlAssertExists "$tmp/execute-must-obey/plan/execute-must-obey/execute/data/guest/default-0/shell-run/yes-1/output.txt"
        rlAssertNotExists "$tmp/execute-must-obey/plan/execute-must-obey/execute/data/guest/default-0/shell-not-run"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
