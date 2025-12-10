#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Prepare"
        rlRun "tmt run -i $tmp provision prepare"
        rlRun "ls -l $tmp"
        rlAssertExists "$tmp/cleanup-test"
    rlPhaseEnd

    rlPhaseStartTest "Finish"
        rlRun "tmt run -i $tmp finish"
        rlRun "ls -l $tmp"
        rlAssertNotExists "$tmp/cleanup-test"
    rlPhaseEnd

    rlPhaseStartTest "Verify prepare and finish step save results"
        rlRun "tmt run -i $tmp --scratch provision prepare finish"

        rlAssertExists "$tmp/prepare/results.yaml"
        rlLogInfo "Content of $tmp/prepare/results.yaml:\n$(cat $tmp/prepare/results.yaml)"
        rlAssertEquals "Finish results exists" \
            "$(yq '[sort_by(.name) | .[] | "\(.name):\(.result)"] | join(" ")' $tmp/prepare/results.yaml)" \
            "default-0 / script #0:pass"

        rlAssertExists "$tmp/finish/results.yaml"
        rlLogInfo "Content of $tmp/finish/results.yaml:\n$(cat $tmp/finish/results.yaml)"
        rlAssertEquals "Finish results exists" \
            "$(yq '[sort_by(.name) | .[] | "\(.name):\(.result)"] | join(" ")' $tmp/finish/results.yaml)" \
            "default-0 / script #0:pass"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
