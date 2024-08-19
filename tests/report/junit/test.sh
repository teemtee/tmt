#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for method in tmt; do
        rlPhaseStartTest "$method"
            rlRun "tmt run -avr execute -h $method report -h junit --file junit.xml 2>&1 >/dev/null | tee output" 2
            rlAssertGrep "2 tests passed, 2 tests failed, 2 tests skipped, 2 infos, 2 warns and 2 errors" "output"
            rlAssertGrep '<testsuite disabled="0" errors="4" failures="2" name="/plan" skipped="2" tests="12"' "junit.xml"
            rlAssertGrep 'fail</failure>' "junit.xml"

            rlRun "xmllint --noout --schema 'tmt-report-junit.xsd' 'junit.xml'" 0 "Checking generated JUnit against the XSD schema"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "rm output junit.xml"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
