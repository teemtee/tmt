#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "root=/var/tmp/tmt"
        rlRun "test_root=\$(mktemp -d)"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Create a couple of runs"
        for id in {001..005}; do
            rlRun "tmt --feeling-safe run --id clean-$id"
            rlAssertExists "$root/clean-$id"
        done
    rlPhaseEnd

    rlPhaseStartTest "Remove last"
        rlRun "tmt clean -v --last"
        rlAssertExists "$root/clean-001"
        rlAssertExists "$root/clean-002"
        rlAssertExists "$root/clean-003"
        rlAssertExists "$root/clean-004"
        rlAssertNotExists "$root/clean-005"
    rlPhaseEnd

    rlPhaseStartTest "Remove selected (full path)"
        rlRun "tmt clean -v --id $root/clean-001"
        rlAssertNotExists "$root/clean-001"
        rlAssertExists "$root/clean-002"
        rlAssertExists "$root/clean-003"
        rlAssertExists "$root/clean-004"
        rlAssertNotExists "$root/clean-005"
    rlPhaseEnd

    rlPhaseStartTest "Remove selected (name)"
        rlRun "tmt clean -v --id clean-002"
        rlAssertNotExists "$root/clean-001"
        rlAssertNotExists "$root/clean-002"
        rlAssertExists "$root/clean-003"
        rlAssertExists "$root/clean-004"
        rlAssertNotExists "$root/clean-005"
    rlPhaseEnd

    rlPhaseStartTest "Skip latest guests and runs"
        rlRun "tmt clean -v --keep 1"
        rlAssertNotExists "$root/clean-001"
        rlAssertNotExists "$root/clean-002"
        rlAssertNotExists "$root/clean-003"
        rlAssertExists "$root/clean-004"
        rlAssertNotExists "$root/clean-005"
    rlPhaseEnd

    rlPhaseStartTest "Create a couple of runs in non-default root workdir"
	export TMT_WORKDIR_ROOT=$test_root
        for id in {001..003}; do
            rlRun "tmt run --id clean-$id"
            rlAssertExists "$test_root/clean-$id"
        done
    rlPhaseEnd

    rlPhaseStartTest "Remove plan in a non-default root wordkir"
        rlRun "tmt clean -v --id clean-002 --workdir-root $test_root"
        rlAssertNotExists "$test_root/clean-002"
        rlAssertExists "$test_root/clean-001"
        rlAssertExists "$test_root/clean-003"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
