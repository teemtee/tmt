#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run --id $run --remove discover -vvv"

        rlAssertGrep "url: https://github.com/beakerlib/httpd" $rlRun_LOG
        rlAssertGrep "url: https://github.com/beakerlib/openssl" $rlRun_LOG
        rlAssertGrep "url: https://github.com/redhat-qe-security/certgen" $rlRun_LOG

        rlRun "grep -A2 'https://github.com/redhat-qe-security/certgen' $rlRun_LOG"

        rlAssertGrep "name: /certgen" $rlRun_LOG
        rlAssertGrep "type: library" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
