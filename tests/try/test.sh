#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "config=$(realpath config)"
        rlRun "export TMT_NO_COLOR=1"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Default Plan"
        rlRun -s "TMT_CONFIG_DIR=$tmp ./local.exp"
        rlAssertGrep "Let's try.*/default/plan" $rlRun_LOG
        rlAssertGrep "Run .* successfully finished. Bye for now!" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "User Plan"
        rlRun -s "TMT_CONFIG_DIR=$config ./try.exp"
        rlAssertGrep "Let's try.*/user/plan" $rlRun_LOG
        rlAssertGrep "Run .* successfully finished. Bye for now!" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Local Plan"
        rlRun -s "./plan.exp"
        rlAssertGrep "Let's try.*/plans/basic" $rlRun_LOG
        rlAssertGrep "Run .* successfully finished. Bye for now!" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verbose Output"
        rlRun -s "TMT_CONFIG_DIR=$config ./verbose.exp"
        rlAssertGrep "custom-prepare" $rlRun_LOG
        rlAssertGrep "fail.*/tests/base/bad" $rlRun_LOG
        rlAssertGrep "pass.*/tests/base/good" $rlRun_LOG
        rlAssertGrep "errr.*/tests/base/weird" $rlRun_LOG
        rlAssertGrep "Run .* successfully finished. Bye for now!" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Report Results"
        rlRun -s "./report.exp"
        rlAssertGrep "fail /tests/base/bad" $rlRun_LOG
        rlAssertGrep "pass /tests/base/good" $rlRun_LOG
        rlAssertGrep "errr /tests/base/weird" $rlRun_LOG
        rlAssertGrep "summary: 6 tests executed" $rlRun_LOG
        rlAssertGrep "summary: 2 tests passed, 2 tests failed and 2 errors" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Keep"
        rlRun -s "./keep.exp" 0 "Quit the session"
        rlAssertGrep "Run .* kept unfinished. See you soon!" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Single Test (default plan)"
        rlRun "pushd tests/core/good"
        rlRun -s "TMT_CONFIG_DIR=$tmp ../../../local.exp" 0 "Try with local"
        rlAssertGrep "Let's try /tests/core/good with /default/plan" $rlRun_LOG
        rlAssertGrep "summary: 1 test executed" $rlRun_LOG
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Three Tests (user plan, verbose)"
        rlRun "pushd tests/core"
        rlRun -s "TMT_CONFIG_DIR=$config ../../verbose.exp" 0 "Try with local"
        rlAssertGrep "Let's try /tests/core/bad, /tests/core/good and /tests/core/weird" $rlRun_LOG
        rlAssertGrep "/user/plan" $rlRun_LOG
        rlAssertGrep "custom-prepare" $rlRun_LOG
        rlAssertGrep "summary: 3 tests executed" $rlRun_LOG
        rlAssertGrep "fail /tests/core/bad" $rlRun_LOG
        rlAssertGrep "pass /tests/core/good" $rlRun_LOG
        rlAssertGrep "errr /tests/core/weird" $rlRun_LOG
        rlAssertNotGrep "fail /tests/base/bad" $rlRun_LOG
        rlAssertNotGrep "pass /tests/base/good" $rlRun_LOG
        rlAssertNotGrep "errr /tests/base/weird" $rlRun_LOG
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "No Test"
        rlRun "pushd no-tests"
        rlRun -s "TMT_CONFIG_DIR=$tmp ../local.exp" 0 "Try with local"
        rlAssertGrep "warn: No tests found under the 'no-tests' directory." $rlRun_LOG
        rlAssertGrep "Let's try something with /default/plan" $rlRun_LOG
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -f config/last-run"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
