#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd special"
    rlPhaseEnd

    rlPhaseStartTest "Check characters are correctly escaped in tmt-report-result output"
        rlRun "tmt run -v -i $run" 0

        # Basic test for special chars
        RESULT_FILE_BASIC="$run/plan/execute/data/guest/default-0/test/0-7-special-characters-in-the-name-1/data/tmt-report-results.yaml"
        rlRun "yq -e '.' $RESULT_FILE_BASIC" 0 "Check the YAML is valid"

        # Get and test the concrete item from the list of subresults
        rlRun "yq -ery '.[] | select(.name == \"/0..7 \\\"special\\\": \\\" characters: *\$@|&>< in: the: name\")' \"$RESULT_FILE_BASIC\" | tee subresult.out"
        rlAssertGrep "name: '/0\.\.7 \\\"special\\\": \\\" characters: \\*\\\$@|&>< in: the: name'" "subresult.out"
        rlAssertGrep "result: pass" "subresult.out"
        rlAssertGrep "end-time: '.*'" "subresult.out"

        # Beakerlib phase names with special chars
        RESULT_FILE_BKRLIB="$run/plan/execute/data/guest/default-0/test/beakerlib-special-names-2/data/tmt-report-results.yaml"
        for phase_name in \
            '/sbin-ldconfig' \
            '/usr-sbin-ldconfig' \
            '/01-some-phase-na-me' \
            '/02-so-me-phase-na-me' \
            /{03..14}-some
        do
            rlRun "yq -ery '.[] | select(.name == \"${phase_name}\")' \"$RESULT_FILE_BKRLIB\" | tee subresult.out"
            rlAssertGrep "name: ${phase_name}" "subresult.out"
            rlAssertGrep "result: pass" "subresult.out"
            rlAssertGrep "end-time: '.*'" "subresult.out"
        done
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm subresult.out" 0 "Remove subresult temporary file"

        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
