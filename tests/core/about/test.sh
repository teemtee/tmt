#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

EXPECTED_PLUGIN_LIST=\
"export.plan:
  - dict
  - json
  - template
  - yaml
export.story:
  - dict
  - json
  - template
  - rst
  - yaml
export.test:
  - dict
  - json
  - nitrate
  - polarion
  - template
  - yaml
package_managers:
  - apk
  - apt
  - dnf
  - dnf5
  - yum
  - rpm-ostree
plan_shapers:
  - max-tests
step.discover:
  - fmf
  - shell
step.execute:
  - tmt
  - upgrade
step.finish:
  - ansible
  - shell
step.prepare:
  - install
  - ansible
  - shell
  - feature
step.provision:
  - artemis
  - virtual.testcloud
  - bootc
  - connect
  - local
  - beaker
  - container
step.report:
  - display
  - html
  - junit
  - polarion
  - reportportal
test.check:
  - avc
  - dmesg
  - watchdog
test.framework:
  - beakerlib
  - shell"


rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
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

    rlPhaseStartSetup "List plugins as YAML"
        rlRun -s "tmt about plugins ls --how yaml"

        # Hello, traveller. Is this test failing for you? Then you
        # probably added new plugin, or changed existing ones, e.g.
        # by renaming their registry or moving plugins around. The
        # test is a sanity one, making sure tmt discovers all it can,
        # updating $EXPECTED_PLUGIN_LIST should turn the tide of
        # misfortune.
        rlAssertEquals "Compare the list of discovered output with the expected one" "$EXPECTED_PLUGIN_LIST" "$(yq -yS '.' $rlRun_LOG)"
    rlPhaseEnd

    rlPhaseStartCleanup
    rlPhaseEnd
rlJournalEnd
