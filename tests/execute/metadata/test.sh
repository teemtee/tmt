#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmt -c cli_context=cli-value -c common_context=new-cli-value run -vi $tmp"
        metadata="$tmp/plan/execute/data/guest/default-0/test-1/metadata.yaml"
        rlRun "cat $metadata" 0 "Check metadata.yaml content"
        rlAssertGrep "name: /test" $metadata
        rlAssertGrep "summary: Simple test" $metadata
        rlAssertGrep "library(epel/epel)" $metadata
        rlAssertGrep "weather: nice" $metadata
        rlAssertGrep "duration: 5m" $metadata
        rlRun "yq .recommend[] $metadata | grep forest" \
            0 "Recommend should be converted to a list"
        # Check context in metadata is the final context
        rlRun "yq .context.plan_context $metadata | grep 'plan-value'" \
        		0 "Context should contain plan's context"
        rlRun "yq .context.cli_context $metadata | grep 'cli-value'" \
        		0 "Context should contain cli's context"
        rlRun "yq .context.common_context $metadata | grep 'new-cli-value'" \
        		0 "Context should have the final value"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
