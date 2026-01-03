#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

TOKEN=$TMT_PLUGIN_REPORT_REPORTPORTAL_TOKEN
URL=$TMT_PLUGIN_REPORT_REPORTPORTAL_URL
PROJECT="$(yq -r '."/has-project".report.project' 'data/project.fmf')"
ARTIFACTS=$TMT_REPORT_ARTIFACTS_URL

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run workdir"
        rlRun "set -o pipefail"
        if [[ -z "$TOKEN" ||  -z "$URL" || -z "$PROJECT" ]]; then
            rlFail "URL, TOKEN and PROJECT must be defined properly" || rlDie
        fi
    rlPhaseEnd

    rlPhaseStartTest "Verify project key is required"
        # Make sure the project key is not set in env var
        TMT_PLUGIN_REPORT_REPORTPORTAL_PROJECT=""

        # Its not defined anywhere else and not defined in the this command
        # An exception should occur
        rlRun -s "tmt run --id $run --scratch --all provision --how container report --verbose --how reportportal plan --default" 2 "Command line without project arg"
        rlAssertGrep "plan failed" $rlRun_LOG
        rlAssertGrep "No ReportPortal project provided." $rlRun_LOG

        # Its not defined anywhere else and not defined in the this plan
        rlRun -s "tmt -c project=1 run --id $run --scratch plan --name /project/missing-project" 2 "plan file without project key"
        rlAssertGrep "plan failed" $rlRun_LOG
        rlAssertGrep "No ReportPortal project provided." $rlRun_LOG

        # Its defined in the command line
        rlRun -s "tmt run --id $run --scratch --all provision --how container report --verbose --how reportportal --project $PROJECT plan --default" 2 "Command line with project arg"
        rlAssertGrep "url: https?://.*\.redhat\.com/ui/#${PROJECT}/launches/all/[0-9]+" $rlRun_LOG -Eq

        # Its defined in the plan file
        rlRun -s "tmt -c project=1 run --id $run --scratch plan --name /project/has-project" 2 "plan file with project key"
        rlAssertGrep "url: https?://.*\.redhat\.com/ui/#${PROJECT}/launches/all/[0-9]+" $rlRun_LOG -Eq

        # Its defined in the env var
        TMT_PLUGIN_REPORT_REPORTPORTAL_PROJECT=$PROJECT
        rlRun -s "tmt run --id $run --scratch --all provision --how container report --verbose --how reportportal plan --default" 2 "command line with project key in env var"
        rlAssertGrep "url: https?://.*\.redhat\.com/ui/#${PROJECT}/launches/all/[0-9]+" $rlRun_LOG -Eq

    rlPhaseEnd


    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove run workdir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
