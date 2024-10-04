#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest 'Test the properties gets propagated to testsuites correctly'
        rlRun "tmt run -avr execute report -h polarion --no-upload --project-id RHELBASEOS --template mytemplate --planned-in RHEL-9.1.0 --arch x86_64 --description mydesc --assignee myassignee --pool-team mypoolteam --platform myplatform --build mybuild --sample-image mysampleimage --logs mylogslocation --compose-id mycomposeid --file xunit.xml 2>&1 >/dev/null | tee output" 2
        rlAssertGrep "1 test passed, 1 test failed and 1 error" "output"
        rlAssertGrep "Maximum test time '2s' exceeded." "xunit.xml"

        # testsuites and testsuite tag attributes
        rlAssertGrep '<testsuites disabled="0" errors="1" failures="1" tests="3"' "xunit.xml"
        rlAssertGrep '<testsuite name="/plan" disabled="0" errors="1" failures="1" skipped="0" tests="3"' "xunit.xml"
        # Main testsuite properties
        rlAssertGrep '<property name="polarion-project-id" value="RHELBASEOS"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-project-span-ids" value="RHELBASEOS,RHELBASEOS"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testrun-title" value="plan_[0-9]\+"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testrun-template-id" value="mytemplate"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-user-id" value="' "xunit.xml"

        # Custom testsuite properties
        rlAssertGrep '<property name="polarion-custom-description" value="mydesc"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-plannedin" value="RHEL-9.1.0"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-assignee" value="myassignee"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-poolteam" value="mypoolteam"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-arch" value="x86_64"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-platform" value="myplatform"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-build" value="mybuild"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-sampleimage" value="mysampleimage"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-logs" value="mylogslocation"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-composeid" value="mycomposeid"/>' "xunit.xml"

        # The testcase properties
        rlAssertGrep '<property name="polarion-testcase-id" value="BASEOS-10913"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testcase-id" value="BASEOS-10914"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testcase-id" value="BASEOS-10915"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testcase-project-id" value="RHELBASEOS"/>' "xunit.xml"
    rlPhaseEnd

    rlPhaseStartTest 'Test the facts properties'
        rlRun "tmt run -avr execute report -h polarion --no-upload --project-id RHELBASEOS --use-facts --file xunit.xml 2>&1 >/dev/null | tee output" 2
        rlAssertGrep '<property name="polarion-custom-hostname" value="' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-arch" value="' "xunit.xml"
    rlPhaseEnd

    rlPhaseStartTest 'The "None" string should never be in a property value'
        rlRun "tmt run -avr execute report -h polarion --no-upload --project-id RHELBASEOS --template '' --planned-in '' --arch '' --description '' --assignee '' --pool-team '' --platform '' --build '' --sample-image '' --logs '' --compose-id '' --file xunit.xml 2>&1 >/dev/null | tee output" 2
        rlAssertNotGrep 'value="None"' "xunit.xml"

        rlRun "export \
        TMT_PLUGIN_REPORT_POLARION_PROJECT_ID= \
        TMT_PLUGIN_REPORT_POLARION_TITLE= \
        TMT_PLUGIN_REPORT_POLARION_DESCRIPTION= \
        TMT_PLUGIN_REPORT_POLARION_TEMPLATE= \
        TMT_PLUGIN_REPORT_POLARION_PLANNED_IN= \
        TMT_PLUGIN_REPORT_POLARION_ASSIGNEE= \
        TMT_PLUGIN_REPORT_POLARION_POOL_TEAM= \
        TMT_PLUGIN_REPORT_POLARION_ARCH= \
        TMT_PLUGIN_REPORT_POLARION_PLATFORM= \
        TMT_PLUGIN_REPORT_POLARION_BUILD= \
        TMT_PLUGIN_REPORT_POLARION_SAMPLE_IMAGE= \
        TMT_PLUGIN_REPORT_POLARION_LOGS= \
        TMT_PLUGIN_REPORT_POLARION_COMPOSE_ID= \
        "
        rlRun "tmt run -avr execute report -h polarion --no-upload --project-id RHELBASEOS --file xunit.xml 2>&1 >/dev/null | tee output" 2
        rlAssertNotGrep 'value="None"' "xunit.xml"
    rlPhaseEnd

    rlPhaseStartTest 'Check the plugin behavior based on setting ENV variables'
        rlRun "export \
        TMT_PLUGIN_REPORT_POLARION_PROJECT_ID=myprojectid \
        TMT_PLUGIN_REPORT_POLARION_TITLE=mytitle \
        TMT_PLUGIN_REPORT_POLARION_DESCRIPTION=mydesc \
        TMT_PLUGIN_REPORT_POLARION_TEMPLATE=mytemplate \
        TMT_PLUGIN_REPORT_POLARION_PLANNED_IN=myplannedin \
        TMT_PLUGIN_REPORT_POLARION_ASSIGNEE=myassignee \
        TMT_PLUGIN_REPORT_POLARION_POOL_TEAM=mypoolteam \
        TMT_PLUGIN_REPORT_POLARION_ARCH=x86_64 \
        TMT_PLUGIN_REPORT_POLARION_PLATFORM=myplatform \
        TMT_PLUGIN_REPORT_POLARION_BUILD=mybuild \
        TMT_PLUGIN_REPORT_POLARION_SAMPLE_IMAGE=mysampleimage \
        TMT_PLUGIN_REPORT_POLARION_LOGS=mylogslocation \
        TMT_PLUGIN_REPORT_POLARION_COMPOSE_ID=mycomposeid \
        "

        rlRun "tmt run -avr execute report -h polarion --no-upload --file xunit.xml 2>&1 >/dev/null | tee output" 2
        # Main testsuite properties
        rlAssertGrep '<property name="polarion-project-id" value="myprojectid"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-project-span-ids" value="myprojectid,RHELBASEOS"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testrun-title" value="mytitle"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testrun-template-id" value="mytemplate"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-user-id" value="' "xunit.xml"

        # Custom testsuite properties
        rlAssertGrep '<property name="polarion-custom-description" value="mydesc"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-plannedin" value="myplannedin"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-assignee" value="myassignee"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-poolteam" value="mypoolteam"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-arch" value="x86_64"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-platform" value="myplatform"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-build" value="mybuild"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-sampleimage" value="mysampleimage"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-logs" value="mylogslocation"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-composeid" value="mycomposeid"/>' "xunit.xml"

        # The testcase properties
        rlAssertGrep '<property name="polarion-testcase-id" value="BASEOS-10913"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testcase-id" value="BASEOS-10914"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testcase-id" value="BASEOS-10915"/>' "xunit.xml"
        rlAssertGrep '<property name="polarion-testcase-project-id" value="RHELBASEOS"/>' "xunit.xml"
    rlPhaseEnd

    rlPhaseStartTest 'Check the plugin behavior based on TMT_PLUGIN_REPORT_POLARION_USE_FACTS env variable'
        # Make sure all ENV variables are unset
        rlRun "unset \
        TMT_PLUGIN_REPORT_POLARION_PROJECT_ID \
        TMT_PLUGIN_REPORT_POLARION_TITLE \
        TMT_PLUGIN_REPORT_POLARION_DESCRIPTION \
        TMT_PLUGIN_REPORT_POLARION_TEMPLATE \
        TMT_PLUGIN_REPORT_POLARION_PLANNED_IN \
        TMT_PLUGIN_REPORT_POLARION_ASSIGNEE \
        TMT_PLUGIN_REPORT_POLARION_POOL_TEAM \
        TMT_PLUGIN_REPORT_POLARION_ARCH \
        TMT_PLUGIN_REPORT_POLARION_PLATFORM \
        TMT_PLUGIN_REPORT_POLARION_BUILD \
        TMT_PLUGIN_REPORT_POLARION_SAMPLE_IMAGE \
        TMT_PLUGIN_REPORT_POLARION_LOGS \
        TMT_PLUGIN_REPORT_POLARION_COMPOSE_ID \
        TMT_PLUGIN_REPORT_POLARION_USE_FACTS \
        "

        # The facts must not be set
        rlRun "export TMT_PLUGIN_REPORT_POLARION_USE_FACTS=0"
        rlRun "tmt run -avr execute report -h polarion --no-upload --project-id RHELBASEOS --file xunit.xml 2>&1 >/dev/null | tee output" 2
        rlAssertNotGrep '<property name="polarion-custom-arch" value="' "xunit.xml"
        rlAssertNotGrep '<property name="polarion-custom-hostname" value="' "xunit.xml"

        # The facts must be set
        rlRun "export TMT_PLUGIN_REPORT_POLARION_USE_FACTS=1"
        rlRun "tmt run -avr execute report -h polarion --no-upload --project-id RHELBASEOS --file xunit.xml 2>&1 >/dev/null | tee output" 2
        rlAssertGrep '<property name="polarion-custom-arch" value="' "xunit.xml"
        rlAssertGrep '<property name="polarion-custom-hostname" value="' "xunit.xml"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm output xunit.xml"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
