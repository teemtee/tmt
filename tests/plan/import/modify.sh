#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd modify-data"
    rlPhaseEnd

    rlPhaseStartTest "Show imported plans"
        rlRun -s "tmt plan show /plans/imported/bare"
        rlAssertNotGrep "environment VARIABLE: foo" $rlRun_LOG

        rlRun -s "tmt plan show /plans/imported/with-environment"
        rlAssertGrep "environment VARIABLE: foo" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Show importing plans"
        # Bare imported + trivial importing + no CLI => no variable
        rlRun -s "tmt plan show                            /importing/bare/dont-modify"
        rlAssertNotGrep "environment VARIABLE: foo" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: bar" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: baz" $rlRun_LOG

        # Bare imported + trivial importing + CLI => CLI wins
        rlRun -s "tmt plan show --environment VARIABLE=baz /importing/bare/dont-modify"
        rlAssertNotGrep "environment VARIABLE: foo" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: bar" $rlRun_LOG
        rlAssertGrep    "environment VARIABLE: baz" $rlRun_LOG

        # Bare imported + enhanced importing + no CLI => importing wins
        rlRun -s "tmt plan show                            /importing/bare/modify"
        rlAssertNotGrep "environment VARIABLE: foo" $rlRun_LOG
        rlAssertGrep    "environment VARIABLE: bar" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: baz" $rlRun_LOG

        # Bare imported + enhanced importing + CLI => CLI wins
        rlRun -s "tmt plan show --environment VARIABLE=baz /importing/bare/modify"
        rlAssertNotGrep "environment VARIABLE: foo" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: bar" $rlRun_LOG
        rlAssertGrep    "environment VARIABLE: baz" $rlRun_LOG

        # Enhanced imported + trivial importing + no CLI => imported wins
        rlRun -s "tmt plan show                            /importing/with-environment/dont-modify"
        rlAssertGrep    "environment VARIABLE: foo" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: bar" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: baz" $rlRun_LOG

        # Enhanced imported + trivial importing + CLI => CLI wins
        rlRun -s "tmt plan show --environment VARIABLE=baz /importing/with-environment/dont-modify"
        rlAssertNotGrep "environment VARIABLE: foo" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: bar" $rlRun_LOG
        rlAssertGrep    "environment VARIABLE: baz" $rlRun_LOG

        # Enhanced imported + enhanced importing + no CLI => importing wins
        rlRun -s "tmt plan show                            /importing/with-environment/modify"
        rlAssertNotGrep "environment VARIABLE: foo" $rlRun_LOG
        rlAssertGrep    "environment VARIABLE: bar" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: baz" $rlRun_LOG

        # Enhanced imported + enhanced importing + CLI => CLI wins
        rlRun -s "tmt plan show --environment VARIABLE=baz /importing/with-environment/modify"
        rlAssertNotGrep "environment VARIABLE: foo" $rlRun_LOG
        rlAssertNotGrep "environment VARIABLE: bar" $rlRun_LOG
        rlAssertGrep    "environment VARIABLE: baz" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Run importing plans"
        # Bare imported + trivial importing + no CLI => no variable
        rlRun -s "tmt run -vvv                            plan --name /importing/bare/dont-modify" 1
        rlAssertNotGrep "out: VARIABLE=foo" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=bar" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=baz" $rlRun_LOG

        # Bare imported + trivial importing + CLI => CLI wins
        rlRun -s "tmt run -vvv --environment VARIABLE=baz plan --name /importing/bare/dont-modify"
        rlAssertNotGrep "out: VARIABLE=foo" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=bar" $rlRun_LOG
        rlAssertGrep    "out: VARIABLE=baz" $rlRun_LOG

        # Bare imported + enhanced importing + no CLI => importing wins
        rlRun -s "tmt run -vvv                            plan --name /importing/bare/modify"
        rlAssertNotGrep "out: VARIABLE=foo" $rlRun_LOG
        rlAssertGrep    "out: VARIABLE=bar" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=baz" $rlRun_LOG

        # Bare imported + enhanced importing + CLI => CLI wins
        rlRun -s "tmt run -vvv --environment VARIABLE=baz plan --name /importing/bare/modify"
        rlAssertNotGrep "out: VARIABLE=foo" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=bar" $rlRun_LOG
        rlAssertGrep    "out: VARIABLE=baz" $rlRun_LOG

        # Enhanced imported + trivial importing + no CLI => imported wins
        rlRun -s "tmt run -vvv                            plan --name /importing/with-environment/dont-modify"
        rlAssertGrep    "out: VARIABLE=foo" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=bar" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=baz" $rlRun_LOG

        # Enhanced imported + trivial importing + CLI => CLI wins
        rlRun -s "tmt run -vvv --environment VARIABLE=baz plan --name /importing/with-environment/dont-modify"
        rlAssertNotGrep "out: VARIABLE=foo" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=bar" $rlRun_LOG
        rlAssertGrep    "out: VARIABLE=baz" $rlRun_LOG

        # Enhanced imported + enhanced importing + no CLI => importing wins
        rlRun -s "tmt run -vvv                            plan --name /importing/with-environment/modify"
        rlAssertNotGrep "out: VARIABLE=foo" $rlRun_LOG
        rlAssertGrep    "out: VARIABLE=bar" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=baz" $rlRun_LOG

        # Enhanced imported + enhanced importing + CLI => CLI wins
        rlRun -s "tmt run -vvv --environment VARIABLE=baz plan --name /importing/with-environment/modify"
        rlAssertNotGrep "out: VARIABLE=foo" $rlRun_LOG
        rlAssertNotGrep "out: VARIABLE=bar" $rlRun_LOG
        rlAssertGrep    "out: VARIABLE=baz" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
