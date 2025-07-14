#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'pushd data'
        rlRun 'set -o pipefail'

        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
    rlPhaseEnd

    rlPhaseStartTest "Check the TMT_DEBUG variable"
        rlRun -s "TMT_DEBUG=3 tmt plan show"
        rlAssertGrep "Using the 'DiscoverFmf' plugin" $rlRun_LOG
        rlRun -s "TMT_DEBUG=weird tmt plan show" 2
        rlAssertGrep "Invalid debug level" $rlRun_LOG
    rlPhaseEnd

    for execute in 'tmt'; do
        tmt="tmt run -avvvr execute --how $execute"

        rlPhaseStartTest "Variable in L1 ($execute)"
            rlRun -s "$tmt plan --name no test --name yes"
            rlAssertGrep '>>>L1<<<' $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "Variable in L2 ($execute)"
            rlRun -s "$tmt plan --name yes test --name no"
            rlAssertGrep '>>>L2<<<' $rlRun_LOG
            rlRun -s "$tmt plan --name yes test --name yes"
            rlAssertGrep '>>>L2<<<' $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "Variable in option ($execute)"
            for plan in yes no; do
                for test in yes no; do
                    rlRun -s "tmt run -avvvr -e STR=O -e INT=0 \
                        execute --how $execute \
                        plan --name $plan \
                        test --name $test"
                    rlAssertGrep '>>>O0<<<' $rlRun_LOG
                done
            done
        rlPhaseEnd

        # Use the same setup as the test above, but instead of defining
        # variables on the command line read them from a YAML file
        rlPhaseStartTest "Variable in YAML file ($execute)"
            for plan in yes no; do
                for test in yes no; do
                    rlRun -s "tmt run -avvvr -e @vars.yaml \
                        execute --how $execute \
                        plan --name $plan \
                        test --name $test"
                    rlAssertGrep '>>>O0<<<' $rlRun_LOG
                done
            done
        rlPhaseEnd

        # Use the same setup as the test above, but instead of defining
        # variables on the command line read them from a DOTENV file
        rlPhaseStartTest "Variable in DOTENV file ($execute)"
            for plan in yes no; do
                for test in yes no; do
                    rlRun -s "tmt run -avvvr -e @vars.env \
                        execute --how $execute \
                        plan --name $plan \
                        test --name $test"
                    rlAssertGrep '>>>O0<<<' $rlRun_LOG
                done
            done
        rlPhaseEnd

        rlPhaseStartTest "Empty YAML environment file ($execute)"
            rlRun -s "tmt run -r -e @empty.yaml"
            rlAssertGrep "warn: Empty environment file" $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "Empty DOTENV environment file ($execute)"
            rlRun -s "tmt run -r -e @empty.env"
            rlAssertGrep "warn: Empty environment file" $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "Variable file outside of fmf root ($execute)"
            rlRun "cp vars.yaml $tmp/out-of-tree-vars.yaml"
            rlRun "fmf_root=$PWD"

            rlRun "pushd $tmp"

            for plan in yes no; do
                for test in yes no; do
                    rlRun -s "tmt --root $fmf_root run -avvvr -e @out-of-tree-vars.yaml \
                        execute --how $execute \
                        plan --name $plan \
                        test --name $test"
                    rlAssertGrep '>>>O0<<<' $rlRun_LOG
                done
            done

            rlRun "popd"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun 'rm -f output' 0 'Removing tmp file'
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
