#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Report unresolved library dependencies"
        rlRun -s "tmt run discover" "2"
        # One library, one test
        rlAssertGrep "Failed to process beakerlib libraries (/bad-library) for test '/tests/1'\.$" "$rlRun_LOG"
        # Two libraries, one test
        rlAssertGrep "Failed to process beakerlib libraries (/wrong-library) for test '/tests/2'\.$" "$rlRun_LOG"
        rlAssertGrep "Failed to process beakerlib libraries (/incorrect-library) for test '/tests/2'\.$" "$rlRun_LOG"
        # One library, two tests
        rlAssertGrep "Failed to process beakerlib libraries (/absent-library) for test '/tests/3', '/tests/4'\.$" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Report unresolved file dependencies"
        # One file dependency, one test
        rlAssertGrep "Failed to process file dependencies (/bad/file/dependency) for test '/tests/1'\.$" "$rlRun_LOG"
        # Two file dependencies, one test
        rlAssertGrep "Failed to process file dependencies (/wrong/file/dependency) for test '/tests/2'\.$" "$rlRun_LOG"
        rlAssertGrep "Failed to process file dependencies (/incorrect/file/dependency) for test '/tests/2'\.$" "$rlRun_LOG"
        # One file dependency, two tests
        rlAssertGrep "Failed to process file dependencies (/absent/file/dependency) for test '/tests/3', '/tests/4'\.$" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
