#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'pushd data'
        rlRun 'set -o pipefail'
    rlPhaseEnd

    rlPhaseStartTest 'Check environment variable is available'
        rlRun -s 'tmt run -rvvv plan --name /plan/single'
        rlAssertGrep 'MYVAR1="MYVAR1_VALUE"' $rlRun_LOG
        rlAssertGrep 'MYVAR2=""' $rlRun_LOG
        rlAssertGrep 'FINISH1="MYVAR1_VALUE"' $rlRun_LOG
        rlAssertGrep 'FINISH2=""' $rlRun_LOG
        rlAssertGrep 'total: 1 test passed' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Check multiple environment variables are available'
        rlRun -s 'tmt run -rvvv plan --name /plan/multiple'
        rlAssertGrep 'MYVAR1="MYVAR1_VALUE"' $rlRun_LOG
        rlAssertGrep 'MYVAR2="MYVAR2_VALUE"' $rlRun_LOG
        rlAssertGrep 'FINISH1="MYVAR1_VALUE"' $rlRun_LOG
        rlAssertGrep 'FINISH2="MYVAR2_VALUE"' $rlRun_LOG
        rlAssertGrep 'total: 1 test passed' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Check "execute" step can override environment variable'
        rlRun -s 'tmt run -rvvv plan --name /plan/execute-override'
        rlAssertGrep 'FINISH1="MYVAR1_OVERRIDE"' $rlRun_LOG
        rlAssertGrep 'FINISH2="MYVAR2_VALUE"' $rlRun_LOG
        rlAssertGrep 'total: 1 test passed' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
