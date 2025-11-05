#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

EXPECTED_PLUGIN_LIST=\
"export.fmfid: dict json template yaml
export.plan: dict json template yaml
export.story: dict json rst template yaml
export.test: dict json nitrate polarion template yaml
package_managers: apk apt bootc dnf dnf5 mock-dnf mock-dnf5 mock-yum rpm-ostree yum
plan_shapers: max-tests repeat
prepare.artifact.providers: brew brew.build brew.nvr brew.task file koji koji.build koji.nvr koji.task
prepare.feature: crb epel fips profile
step.cleanup: tmt
step.discover: fmf shell
step.execute: tmt upgrade
step.finish: ansible shell
step.prepare: ansible artifact feature install shell
step.provision: artemis beaker bootc connect container local mock virtual.testcloud
step.report: display html junit polarion reportportal
test.check: avc coredump dmesg internal/abort internal/guest internal/interrupt internal/invocation internal/permission internal/timeout journal watchdog
test.framework: beakerlib shell"


rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlRun "export LANG=C"
        rlRun "tmpdir=$(mktemp -d)"

        rlRun "echo \"$EXPECTED_PLUGIN_LIST\" > $tmpdir/expected-plugin-list.txt"
    rlPhaseEnd

    rlPhaseStartTest "List plugins as human-readable output"
        rlRun -s "tmt about plugin ls"

        # Just a brief check, hard to test expected formatting
        rlAssertGrep "Export plugins for story" $rlRun_LOG
        rlAssertGrep "Export plugins for plan" $rlRun_LOG
        rlAssertGrep "Export plugins for test" $rlRun_LOG
        rlAssertGrep "Test check plugins" $rlRun_LOG
        rlAssertGrep "Test framework plugins" $rlRun_LOG
        rlAssertGrep "Plan shapers" $rlRun_LOG
        rlAssertGrep "Package manager plugins" $rlRun_LOG
        rlAssertGrep "Discover step plugins" $rlRun_LOG
        rlAssertGrep "Provision step plugins" $rlRun_LOG
        rlAssertGrep "Prepare step plugins" $rlRun_LOG
        rlAssertGrep "Execute step plugins" $rlRun_LOG
        rlAssertGrep "Finish step plugins" $rlRun_LOG
        rlAssertGrep "Report step plugins" $rlRun_LOG
    rlPhaseEnd

    # Hello, traveller. Is this test failing for you? Then you
    # probably added new plugin, or changed existing ones, e.g.
    # by renaming their registry or moving plugins around. The
    # test is a sanity one, making sure tmt discovers all it can,
    # updating $EXPECTED_PLUGIN_LIST should turn the tide of
    # misfortune.
    rlPhaseStartTest "List plugins as YAML"
        rlRun -s "tmt about plugins ls --how yaml"
        # Make sure the dict is sorted by the keys and its values (list of strings) is also sorted
        rlRun "yq '. | to_entries | [.[] | \"\\(.key): \\(.value | sort | join(\\\" \\\"))\"] | sort | .[]' $rlRun_LOG > $tmpdir/actual-plugin-list.txt"

        rlRun "diff -u $tmpdir/expected-plugin-list.txt $tmpdir/actual-plugin-list.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $tmpdir"
    rlPhaseEnd
rlJournalEnd
