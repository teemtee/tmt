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
            rlAssertGrep "5 tests passed, 5 tests failed and 2 errors" "output"
            rlAssertGrep '00:00:00 pass /test/shell/escape"<speci&l>_chars (on default-0)' "output"
            rlAssertGrep '<testsuite name="/plan" disabled="0" errors="2" failures="5" skipped="0" tests="12"' "junit.xml"
            rlAssertGrep 'fail</failure>' "junit.xml"

            # Test the escape of special characters
            rlAssertGrep '<testcase name="/test/shell/escape&quot;&lt;speci&amp;l&gt;_chars">' "junit.xml"
            rlAssertGrep '<system-out>&lt;speci&amp;l&gt;"chars and control chars</system-out>' "junit.xml"

            # Check there is no schema problem reported
            rlAssertNotGrep 'The generated XML output is not a valid XML file or it is not valid against the XSD schema\.' "output"
        rlPhaseEnd

        rlPhaseStartTest "[$method] Check the flavor argument is working"
            rlRun "tmt run -avr execute -h $method report -h junit --file junit.xml --flavor default 2>&1 >/dev/null | tee output" 2
            rlAssertGrep "5 tests passed, 5 tests failed and 2 errors" "output"

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

        rlPhaseStartTest "[$method] Check the 'custom' flavor and context for subresults"
            rlRun "tmt run -avr execute -h $method report -h junit --file custom-subresults-template-out.xml --template-path custom-subresults.xml.j2 --flavor custom 2>&1 >/dev/null | tee output" 2

            # Beakerlib subresults
            rlAssertGrep '<subresult name="/Test" outcome="fail"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/Test" outcome="pass"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/phase-setup" outcome="pass"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/phase-test-pass" outcome="pass"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/phase-test-fail" outcome="fail"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/extra-tmt-report-result/good" outcome="pass"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/extra-tmt-report-result/bad" outcome="fail"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/extra-tmt-report-result/weird" outcome="warn"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/extra-tmt-report-result/skip" outcome="skip"/>' "custom-subresults-template-out.xml"

            # Chosen shell subresults
            rlAssertGrep '<subresult name="/fail-subtest/good" outcome="pass"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/pass-subtest/good0" outcome="pass"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<subresult name="/skip-subtest/extra-skip" outcome="skip"/>' "custom-subresults-template-out.xml"
            rlAssertGrep '<result name="/test/shell/subresults/skip" disabled="0" errors="0" failures="0" skipped="1" tests="2" time="0" outcome="pass"' "custom-subresults-template-out.xml"
            rlAssertGrep '<result name="/test/shell/subresults/sleep" disabled="0" errors="0" failures="1" skipped="0" tests="2" time="5"' "custom-subresults-template-out.xml"

            rlAssertGrep '<subresult name="/fail-subtest/good" outcome="pass"/>' "custom-subresults-template-out.xml"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "rm output junit.xml custom-template-out.xml custom-subresults-template-out.xml"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
