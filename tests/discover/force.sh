#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1




assert_discover(){
    rlAssertGrep " 3 tests selected" "$rlRun_LOG" -F
    test_yaml="$workdir/run/plans/default/discover/tests.yaml"
    if [ "$1" == "old" ]; then
        do_assert=rlAssertNotGrep
    else
        do_assert=rlAssertGrep
    fi
    $do_assert "unique-package-name-foo" "$test_yaml" -F
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "workdir=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp -r data $workdir"
        rlRun "pushd $workdir/data"
    rlPhaseEnd

    plan="plans --default"

    rlPhaseStartTest
        rlRun -s "tmt run --id $workdir/run $plan discover -fv"
        assert_discover "old"
        # Add new require
        echo 'require: [unique-package-name-foo]' >> tests.fmf

        # Force run should discover new require
        rlRun -s "tmt run --id $workdir/run $plan discover -fv"
        assert_discover
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'popd'
        rlRun "rm -rf $workdir" 0 'Remove tmp directory'
    rlPhaseEnd
rlJournalEnd
