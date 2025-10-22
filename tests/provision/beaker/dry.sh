#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Verify that beaker-watchdog is set to panic=ignore by default"
        rlRun -s "tmt run --dry provision --how beaker --image Fedora-42 plan --default"
        rlAssertGrep 'watchdog panic="ignore"/' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify that beaker panic-watchdog does not break other hardware requirements"
        rlRun -s "tmt run --dry provision --how beaker --hardware beaker.pool=best-pool --hardware beaker.panic-watchdog=False --image Fedora-42 plan --default"
        rlAssertGrep 'watchdog panic="ignore"/' $rlRun_LOG
        rlAssertGrep 'pool op="==" value="best-pool"/' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify that beaker-watchdog config is not included when beaker panic-watchdog is True"
        rlRun -s "tmt run --dry provision --how beaker --hardware beaker.panic-watchdog=True --image Fedora-42 plan --default"
        rlAssertNotGrep 'watchdog panic="ignore"/' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify beaker panic-watchdog hardware schema option works"
        rlRun -s "tmt run --dry plan --name /plan/watchdog"
        rlAssertNotGrep 'watchdog panic="ignore"/' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify that beaker-job-group is passed correctly to dry beaker job"
        rlRun -s "tmt run --dry provision --how beaker --beaker-job-group test-group --image Fedora-42 plan --default"
        rlAssertGrep 'group="test-group"' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify that beaker-job-group is not shown when not specified"
        rlRun -s "tmt run --dry provision --how beaker --image Fedora-42 plan --default"
        rlAssertNotGrep 'group="test-group"' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
