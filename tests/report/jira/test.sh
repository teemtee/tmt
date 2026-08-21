#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest 'Plugin is listed in report --help'
        rlRun "tmt run report --help 2>&1 | tee output"
        rlAssertGrep "jira" "output"
    rlPhaseEnd

    rlPhaseStartTest 'Dry run completes without error'
        rlRun "tmt --feeling-safe run \
            provision --how local \
            discover --how fmf --test '/test/pass$' \
            execute \
            report --how jira \
                --url https://issues.redhat.com \
                --user me@example.com \
                --token dummy \
                --project-id RHELTEST \
                --compose-id RHEL-10.3-20260817.0 \
                --fix-version rhel-10.3 \
                --dry \
            2>&1 | tee output" 0
    rlPhaseEnd

    rlPhaseStartTest 'Missing required options produce a clear error'
        rlRun "tmt --feeling-safe run \
            provision --how local \
            discover --how fmf --test '/test/pass$' \
            execute \
            report --how jira \
            2>&1 | tee output" 2
        rlAssertGrep "Missing required Jira options" "output"
    rlPhaseEnd

    rlPhaseStartTest 'Required options can be set via environment variables'
        rlRun "TMT_PLUGIN_REPORT_JIRA_URL=https://issues.redhat.com \
            TMT_PLUGIN_REPORT_JIRA_USER=me@example.com \
            TMT_PLUGIN_REPORT_JIRA_TOKEN=dummy \
            TMT_PLUGIN_REPORT_JIRA_PROJECT_ID=RHELTEST \
            tmt --feeling-safe run \
            provision --how local \
            discover --how fmf --test '/test/pass$' \
            execute \
            report --how jira \
                --compose-id RHEL-10.3-20260817.0 \
                --fix-version rhel-10.3 \
                --dry \
            2>&1 | tee output" 0
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
