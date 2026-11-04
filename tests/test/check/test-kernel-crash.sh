#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "run=\$(mktemp -d -p /var/tmp)"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Kernel crash check without a real panic"
        rlRun "tmt run --id $run -a -vv provision -h $PROVISION_HOW test -n '^/kernel-crash/(harmless|restart)$'"
        rlRun "results=$run/plan/execute/results.yaml"
        rlRun "yq -e 'length == 2' $results"
        rlRun "yq -e '[.[] | select(.result != \"pass\")] | length == 0' $results"
        rlRun "yq -e '[.[] | select(.name == \"/kernel-crash/restart\") | .check[] | select(.name == \"kernel-crash\")] | length == 2' $results"
        rlRun "yq -e '[.[] | .check[] | select(.name == \"kernel-crash\") | select(.event != \"after-recovery\")] | length == 0' $results"
        rlRun "report=$run/plan/execute/data/guest/default-0/kernel-crash/restart-2/data/kernel-crash.json"
        rlRun "jq -e '.version == 1 and (.reports | length == 2)' $report"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
