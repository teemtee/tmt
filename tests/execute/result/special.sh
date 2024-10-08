#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd special"
    rlPhaseEnd

    rlPhaseStartTest "Check characters are correctly escaped in tmt-report-result output"
        rlRun -s "tmt run -v -i $run" 0

        RESULT_FILE="$run/special-chars/execute/data/guest/default-0/0-7-special-characters-in-the-name-1/data/tmt-report-results.yaml"
        rlRun "yq -e '.' $RESULT_FILE" 0 "Check the YAML is valid"

        rlAssertGrep 'name: "/0\.\.7 \\"special\\": \\" characters: \*\$@|&>< in: the: name"' "$RESULT_FILE"
        rlAssertGrep "result: \"pass\"" "$RESULT_FILE"
        rlAssertGrep "end-time: \".*\"" "$RESULT_FILE"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
