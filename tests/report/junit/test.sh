#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for method in tmt; do
        rlPhaseStartTest "[$method] Basic format checks"
            rlRun "tmt run -avr execute -h $method report -h junit --file junit.xml 2>&1 >/dev/null | tee output" 2
            rlAssertGrep "3 tests passed, 2 tests failed and 2 errors" "output"
            rlAssertGrep '00:00:00 pass /test/shell/escape"<speci&l>_chars (on default-0)' "output"
            rlAssertGrep '<testsuite name="/plan" disabled="0" errors="2" failures="2" skipped="0" tests="7"' "junit.xml"
            rlAssertGrep 'fail</failure>' "junit.xml"

            # Test the escape of special characters
            rlAssertGrep '<testcase name="/test/shell/escape&quot;&lt;speci&amp;l&gt;_chars">' "junit.xml"
            rlAssertGrep '<system-out>&lt;speci&amp;l&gt;"chars' "junit.xml"

            # Check there is no schema problem reported
            rlAssertNotGrep 'The generated XML output is not a valid XML file or it is not valid against the XSD schema\.' "output"
        rlPhaseEnd

        rlPhaseStartTest "[$method] Check the flavor argument is working"
            rlRun "tmt run -avr execute -h $method report -h junit --file junit.xml --flavor default 2>&1 >/dev/null | tee output" 2
            rlAssertGrep "3 tests passed, 2 tests failed and 2 errors" "output"

            # Check there is no schema problem reported
            rlAssertNotGrep 'The generated XML output is not a valid XML file or it is not valid against the XSD schema\.' "output"
        rlPhaseEnd

        rlPhaseStartTest "[$method] Check the mutually exclusive arguments"
            rlRun "tmt run -avr execute -h $method report -h junit --file junit.xml --flavor custom 2>&1 >/dev/null | tee output" 2
            rlAssertGrep "The 'custom' flavor requires the '--template-path' argument." "output"

            rlRun "tmt run -avr execute -h $method report -h junit --file junit.xml --template-path custom.xml.j2 2>&1 >/dev/null | tee output" 2
            rlAssertGrep "The '--template-path' can be used only with '--flavor=custom'." "output"

        rlPhaseEnd

        rlPhaseStartTest "[$method] Check the 'custom' flavor with a custom XML template"
            rlRun "tmt run -avr execute -h $method report -h junit --file custom-template-out.xml --template-path custom.xml.j2 --flavor custom 2>&1 >/dev/null | tee output" 2

            # There must not be a schema check when using a custom flavor
            rlAssertGrep "The 'custom' JUnit flavor is used, you are solely responsible for the validity of the XML schema\." "output"

            rlAssertGrep '<test name="/test/beakerlib/fail" value="fail"/>' "custom-template-out.xml"
            rlAssertGrep '<test name="/test/beakerlib/pass" value="pass"/>' "custom-template-out.xml"
            rlAssertGrep '<test name="/test/shell/pass" value="pass"/>' "custom-template-out.xml"
            rlAssertGrep '<test name="/test/shell/timeout" value="error"/>' "custom-template-out.xml"
            rlAssertGrep '<test name="/test/shell/escape&quot;&lt;speci&amp;l&gt;_chars" value="pass"/>' "custom-template-out.xml"
        rlPhaseEnd

        rlPhaseStartTest "[$method] The 'custom' flavor with a custom **non-XML** template must not work"
            rlRun "tmt run -avr execute -h $method report -h junit --file custom-template-out.xml --template-path non-xml-custom.j2 --flavor custom 2>&1 >/dev/null | tee output" 2

            rlAssertGrep 'The generated XML output is not a valid XML file.' "output"
        rlPhaseEnd

        rlPhaseStartTest "[$method] Check the 'subresults' flavor"
            rlRun "tmt run -avr execute -h $method report -h junit --file subresults-out.xml --flavor subresults 2>&1 >/dev/null | tee output" 2

            # Parent result recorded in testuite tag
            rlAssertGrep '<testsuite name="/test/beakerlib/fail" disabled="0" errors="1" failures="0" skipped="0" tests="1"' "subresults-out.xml"
            rlAssertGrep '<testsuite name="/test/beakerlib/pass" disabled="0" errors="0" failures="0" skipped="0" tests="1" ' "subresults-out.xml"
            rlAssertGrep '<testsuite name="/test/shell/fail" disabled="0" errors="1" failures="0" skipped="0" tests="1"'

            # Parent result testsuite must have its respective testcase tag
            rlAssertGrep '<testcase name="/test/beakerlib/fail">' "subresults-out.xml"
            rlAssertGrep '<testcase name="/test/beakerlib/pass">' "subresults-out.xml"

            # TODO: Add check for additional subresults as soon as they get saved by:
            # - https://github.com/teemtee/tmt/pull/3200
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "rm output junit.xml custom-template-out.xml"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
