#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data-plan-of-plans"
    rlPhaseEnd

    rlPhaseStartTest "replace/first-plan-only"
        rlRun -s "tmt plan ls /plans/replace/first-plan-only"

        rlAssertGrep "/plans/replace/first-plan-only" $rlRun_LOG
        rlAssertEquals "Only one plan is listed" "$(wc -l $rlRun_LOG | awk '{print $1}')" "1"
    rlPhaseEnd

    rlPhaseStartTest "replace/single-plan-only"
        rlRun -s "tmt plan ls /plans/replace/single-plan-only" 2

        rlAssertGrep "Cannot import multiple plans through '/plans/replace/single-plan-only', may import only single plan, and already imported '/plans/provision/artemis/sanity/basic'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "replace/all-plans"
        rlRun -s "tmt plan ls /plans/replace/all-plans" 2

        rlAssertGrep "Cannot import multiple plans through '/plans/replace/all-plans', already replacing '/plans/replace/all-plans' with imported '/plans/provision/artemis/sanity/basic'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "become-parent/first-plan-only"
        rlRun -s "tmt plan ls /plans/become-parent/first-plan-only"

        rlAssertGrep "/plans/become-parent/first-plan-only/plans/provision/artemis/sanity/basic" $rlRun_LOG
        rlAssertEquals "Only one plan is listed" "$(wc -l $rlRun_LOG | awk '{print $1}')" "1"
    rlPhaseEnd

    rlPhaseStartTest "become-parent/single-plan-only"
        rlRun -s "tmt plan ls /plans/become-parent/single-plan-only" 2

        rlAssertGrep "Cannot import multiple plans through '/plans/become-parent/single-plan-only', may import only single plan, and already imported '/plans/provision/artemis/sanity/basic'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "become-parent/all-plans"
        rlRun -s "tmt plan ls /plans/become-parent/all-plans"

        rlAssertGrep "/plans/become-parent/all-plans/plans/provision/artemis" $rlRun_LOG
        rlAssertGrep "/plans/become-parent/all-plans/plans/provision/beaker" $rlRun_LOG
        rlAssertGrep "/plans/become-parent/all-plans/plans/provision/bootc" $rlRun_LOG
        rlAssertGrep "/plans/become-parent/all-plans/plans/provision/connect" $rlRun_LOG
        rlAssertGrep "/plans/become-parent/all-plans/plans/provision/container" $rlRun_LOG
        rlAssertGrep "/plans/become-parent/all-plans/plans/provision/local" $rlRun_LOG
        rlAssertGrep "/plans/become-parent/all-plans/plans/provision/virtual" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
