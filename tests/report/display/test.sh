#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
    rlPhaseEnd

    rlPhaseStartTest "Check guest display modes"
        # Two cases to check the default "auto", one with a single guest, other with multiple...
        rlRun -s "tmt run -av --scratch --id $tmp plan -n singlehost report -h display"
        rlAssertGrep "pass /test$" "$rlRun_LOG"

        rlRun -s "tmt run -av --scratch --id $tmp plan -n multihost report -h display"
        rlAssertGrep "pass /test (on guest-1)$" "$rlRun_LOG"
        rlAssertGrep "pass /test (on guest-2)$" "$rlRun_LOG"

        # ...then "always", ...
        rlRun -s "tmt run -av --scratch --id $tmp plan -n singlehost report -h display --display-guest always"
        rlAssertGrep "pass /test (on default-0)$" "$rlRun_LOG"

        # ... and "never".
        rlRun -s "tmt run -av --scratch --id $tmp plan -n multihost report -h display --display-guest never"
        rlAssertGrep "pass /test$" "$rlRun_LOG"
        rlAssertGrep "pass /test$" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp"
    rlPhaseEnd
rlJournalEnd
