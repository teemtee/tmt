#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Pruning"
        rlRun -s "tmt run --id $run -vvv --debug --until report"
        lib_path=$(grep 'Library database/mariadb is copied into' "$rlRun_LOG"|rev|cut -d' ' -f1|rev)
        rlAssertExists "${lib_path}/mariadb"
        rlAssertNotExists "${lib_path}/postgresql"
        rlAssertNotExists "${lib_path}/mysql"
        rlRun "tmt run --id $run finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
