#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd step-inheritance"
    rlPhaseEnd

    rlPhaseStartTest "Inherit report step only"
        rlRun -s "tmt plan show /inherit-report-only"
        rlAssertGrep "how: junit" $rlRun_LOG
        rlAssertGrep "file: /tmp/results.xml" $rlRun_LOG
        # Should only have report from local plan since remote has no report step
        rlRun "tmt plan export /inherit-report-only > exported.yaml"
        rlAssertGrep "how: junit" exported.yaml
        rlAssertGrep "file: /tmp/results.xml" exported.yaml
    rlPhaseEnd

    rlPhaseStartTest "Inherit and merge with existing remote report step"
        rlRun -s "tmt plan show /inherit-and-merge-report"
        # Should have both the original remote report step and the local one
        rlAssertGrep "how: display" $rlRun_LOG  # from remote plan
        rlAssertGrep "how: junit" $rlRun_LOG     # from local plan
        rlAssertGrep "file: /tmp/local-results.xml" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "No step inheritance (control test)"
        rlRun -s "tmt plan show /no-step-inheritance"
        # Should only have the remote plan's report step, not the local one
        rlAssertGrep "how: display" $rlRun_LOG  # from remote plan
        rlAssertNotGrep "how: junit" $rlRun_LOG  # local step should not be inherited
        rlAssertNotGrep "/tmp/control-results.xml" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -f exported.yaml"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
