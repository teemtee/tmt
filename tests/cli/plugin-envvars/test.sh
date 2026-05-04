#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlRun "export LANG=C"
        rlRun "rundir=$(mktemp -d)"

        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Verify plugin envvars are delivered"
        rlRun "run_tmt=\"tmt -vvv --feeling-safe --log-topic=cli-invocations run --id $rundir --scratch\""

        rlRun -s "$run_tmt"
        rlAssertGrep "ReportPlugin.delegate\(step=report, data=None, raw_data=\{'how': 'html', 'absolute-paths': False, 'display-guest': 'auto', 'name': 'default-0'\}\)" $rundir/log.txt -E

        rlRun -s "TMT_PLUGIN_REPORT_HTML_ABSOLUTE_PATHS=1 TMT_PLUGIN_REPORT_HTML_FILE=/tmp/foo TMT_PLUGIN_REPORT_HTML_DISPLAY_GUEST=never $run_tmt"
        rlAssertGrep "ReportPlugin.delegate\(step=report, data=None, raw_data=\{'how': 'html', 'absolute-paths': True, 'display-guest': 'never', 'name': 'default-0', 'file': '/tmp/foo'\}\)" $rundir/log.txt -E
    rlPhaseEnd

    rlPhaseStartTest "Verify unknown plugins are reported"
        rlRun -s "TMT_PLUGIN_REPORT_XHTML_DISPLAY_GUEST=never $run_tmt"

        rlAssertGrep "warn: Found environment variable for plugin 'report/xhtml', but the plugin was not found. The following environment variable will have no effect: TMT_PLUGIN_REPORT_XHTML_DISPLAY_GUEST" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify unused envvars are reported"
        rlRun -s "TMT_PLUGIN_REPORT_DISPLAY_DISPLAY_GUEST=never $run_tmt"

        rlAssertGrep "warn: Found environment variable for plugin 'report/display', but the plugin is not used by the plan '/'. The following environment variable will have no effect: TMT_PLUGIN_REPORT_DISPLAY_DISPLAY_GUEST" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify unknown options are reported"
        rlRun -s "TMT_PLUGIN_REPORT_HTML_HIDE_GUEST=never $run_tmt" 2

        rlAssertGrep "Failed to find the 'hide-guest' key of the 'report/html' plugin." $rlRun_LOG
    rlPhaseEnd

# Disabled: report/reportportal ignores `--dry`, we can't have it connecting anywhere.
#    rlPhaseStartTest "Verify multi-value plugin option"
#        rlRun "run_tmt_reportportal=\"tmt --context report-portal=1 -vvv --feeling-safe --log-topic=cli-invocations run --id $rundir --scratch --dry\""
#
#        rlRun -s "TMT_PLUGIN_REPORT_REPORTPORTAL_UPLOAD_LOG_PATTERN=\"cool.log my-special-log\" $run_tmt_reportportal"
#        rlAssertGrep "ReportPlugin.delegate\(step=report, data=None, raw_data=\{'how': 'reportportal',.*'upload-log-pattern': \('cool.log', 'my-special-log'\).*\)" $rundir/log.txt -E
#    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $rundir"
    rlPhaseEnd
rlJournalEnd
