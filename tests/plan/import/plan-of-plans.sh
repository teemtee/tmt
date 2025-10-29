#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data-plan-of-plans"
    rlPhaseEnd

    rlPhaseStartTest "replace/first-plan-only"
        rlRun -s "tmt plan ls /plans/replace/first-plan-only"

        rlAssertGrep "^/plans/replace/first-plan-only$" $rlRun_LOG -E
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/artemis.*' through '/plans/replace/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/beaker.*' through '/plans/replace/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/bootc' through '/plans/replace/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/connect' through '/plans/replace/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/container.*' through '/plans/replace/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/local' through '/plans/replace/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/virtual.*' through '/plans/replace/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
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

        rlAssertGrep "^/plans/become-parent/first-plan-only/plans/provision/artemis/sanity/basic$" $rlRun_LOG -E
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/artemis.*' through '/plans/become-parent/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/beaker.*' through '/plans/become-parent/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/bootc' through '/plans/become-parent/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/connect' through '/plans/become-parent/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/container.*' through '/plans/become-parent/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/local' through '/plans/become-parent/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
        rlAssertGrep "warn: Cannot import remote plan '/plans/provision/virtual.*' through '/plans/become-parent/first-plan-only', already imported '/plans/provision/artemis/.*' as the first plan." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "become-parent/single-plan-only"
        rlRun -s "tmt plan ls /plans/become-parent/single-plan-only" 2

        rlAssertGrep "Cannot import multiple plans through '/plans/become-parent/single-plan-only', may import only single plan, and already imported '/plans/provision/artemis/sanity/basic'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "become-parent/all-plans"
        rlRun -s "tmt plan ls /plans/become-parent/all-plans"

        rlAssertGrep "^/plans/become-parent/all-plans/plans/provision/artemis" $rlRun_LOG -E
        rlAssertGrep "^/plans/become-parent/all-plans/plans/provision/beaker" $rlRun_LOG -E
        rlAssertGrep "^/plans/become-parent/all-plans/plans/provision/bootc" $rlRun_LOG -E
        rlAssertGrep "^/plans/become-parent/all-plans/plans/provision/connect" $rlRun_LOG -E
        rlAssertGrep "^/plans/become-parent/all-plans/plans/provision/container" $rlRun_LOG -E
        rlAssertGrep "^/plans/become-parent/all-plans/plans/provision/local" $rlRun_LOG -E
        rlAssertGrep "^/plans/become-parent/all-plans/plans/provision/virtual" $rlRun_LOG -E

        # Make sure the filter works on the expanded plan names also
        # If we did not specify import-before-filter it should still fail
        rlRun -s "tmt plan ls /plans/become-parent/all-plans/plans"
        rlAssertNotGrep "^/plans/become-parent/all-plans/plans" $rlRun_LOG -E
        # But if we do, the filter should apply afterwards
        rlRun -s "tmt --import-before-filter plan ls /plans/become-parent/all-plans/plans"
        rlAssertGrep "^/plans/become-parent/all-plans/plans/provision/artemis" $rlRun_LOG -E
        # Some plans are intentionally broken, make sure that they are reported
        rlAssertGrep "Failed to import plan '/plans/become-parent/single-plan-only'" $rlRun_LOG -E
        rlAssertGrep "Failed to import plan '/plans/replace/all-plans'" $rlRun_LOG -E
        rlAssertGrep "Failed to import plan '/plans/replace/single-plan-only'" $rlRun_LOG -E
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
