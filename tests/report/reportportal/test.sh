#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

TOKEN=$TMT_PLUGIN_REPORT_REPORTPORTAL_TOKEN
URL=$TMT_PLUGIN_REPORT_REPORTPORTAL_URL
PROJECT="$(yq -r .report.project 'data/plan.fmf')"
ARTIFACTS=$TMT_REPORT_ARTIFACTS_URL

PLAN_PREFIX='/plan'
PLAN_STATUS='FAILED'
TEST_PREFIX=''

# TODO: Subresults for beakerlib
declare -A test=([1,'uuid']="" [1,'name']='/test/bad'        [1,'status']='FAILED'
                 [2,'uuid']="" [2,'name']='/test/good'       [2,'status']='PASSED'
                 [3,'uuid']="" [3,'name']='/test/subresults' [3,'status']='FAILED'
                 [4,'uuid']="" [4,'name']='/subtest/good' [4,'status']='PASSED'
                 [5,'uuid']="" [5,'name']='/subtest/fail' [5,'status']='FAILED'
                 [6,'uuid']="" [6,'name']='/subtest/weird' [6,'status']='FAILED'
                 [7,'uuid']="" [7,'name']='/test/subresults-restraint/subtest-restraint/good' [7,'status']='PASSED'
                 [8,'uuid']="" [8,'name']='/test/subresults-restraint/subtest-restraint/fail' [8,'status']='FAILED'
                 [9,'uuid']="" [9,'name']='/test/subresults-restraint/subtest-restraint/weird' [9,'status']='FAILED'
                 [10,'uuid']="" [10,'name']='/test/weird'      [10,'status']='FAILED')
DIV="|"


##
# Read and verify reported launch name, id and uuid from $rlRun_LOG
#
# GLOBALS:
# << $launch_name
# >> $launch_uuid, $launch_id
#
function identify_launch(){
    rlLog "Verify and get launch data"

    rlAssertGrep "launch: $launch_name" $rlRun_LOG
    launch_uuid=$(rlRun "grep -A1 'launch:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
    regex='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if [[ ! $launch_uuid =~ $regex ]]; then
        launch_uuid=$(rlRun "grep -A2 'launch:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
    fi

    rlAssertNotEquals "Assert the launch UUID is not empty" "$launch_uuid" ""
    launch_id=$(rlRun "grep 'url:' $rlRun_LOG | awk '{print \$NF}' | xargs basename")
    rlAssertNotEquals "Assert the launch ID is not empty" "$launch_id" ""
}


##
# Read and verify reported suite name and uuid from $rlRun_LOG
#
# GLOBALS:
# << $suite_name
# >> $suite_uuid
function identify_suite(){
    rlLog "Verify and get suite data"

    rlAssertGrep "suite: $suite_name" $rlRun_LOG
    suite_uuid=$(rlRun "grep -A1 'suite:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
    rlAssertNotEquals "Assert the suite UUID is not empty" "$suite_uuid" ""
}

##
# Read and verify reported test names and uuids from $rlRun_LOG
#
# GLOBALS:
# >> $test_uuid[1..10], $test_fullname[1..10]
function identify_tests(){
    rlLog "Verify and get test data"

    for i in {1..10}; do
        test_fullname[$i]=${TEST_PREFIX}${test[$i,'name']}

        rlAssertGrep " \(sub-\)\?test: ${test_fullname[$i]}" $rlRun_LOG
        rlAssertGrep "test: ${test_fullname[$i]}" $rlRun_LOG
        test_uuid[$i]=$(rlRun "grep -m$i -A1 ' \(sub-\)\?test:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
        rlAssertNotEquals "Assert the test$i UUID is not empty" "${test_uuid[$i]}" ""
        test[$i,'uuid']=${test_uuid[$i]}
    done
}


##
# Proceed GET request via ReportPortal REST API and verify the response
#
# ARGUMENT:
#   request_url
function rest_api(){
    rlLog "REST API request (GET $1)"
    response=$(curl --write-out "$DIV%{http_code}" --silent -X GET "$1" -H  "Accept: */*" -H  "Authorization: Bearer $TOKEN")

    response_code=${response##*"$DIV"}
    response=${response%"$DIV"*}
    if [[ $response_code -ge 300 ]]; then
        rlFail "Request responded with an error: $response"
    fi

    echo "$response"
}



rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run workdir"
        rlRun "set -o pipefail"
        if [[ -z "$TOKEN" ||  -z "$URL" || -z "$PROJECT" ]]; then
            rlFail "URL, TOKEN and PROJECT must be defined properly" || rlDie
        fi
    rlPhaseEnd

    echo -e "\n\n\n::   PART 1\n"

    rlPhaseStartTest "Core Functionality"
        launch_name=$PLAN_PREFIX
        launch_status=$PLAN_STATUS

        # TMT RUN
        rlLogInfo "A run with default setup"
        rlRun -s "tmt run --id $run --verbose --all" 2
        rlAssertGrep "url: https?://.*\.redhat\.com/ui/#${PROJECT}/launches/all/[0-9]+" $rlRun_LOG -Eq
        identify_launch  # >> $launch_uuid, $launch_id
        identify_tests   # >> $test_uuid[1..10], $test_fullname[1..10]
    rlPhaseEnd


    rlPhaseStartTest "Core Functionality - DEFAULT SETUP"

        # REST API | [GET] launch-controller | uuid
        rlLogInfo "Get info about the launch"
        response=$(rest_api "$URL/api/v1/$PROJECT/launch/uuid/$launch_uuid")
        rlAssertEquals "Assert the URL ID of launch is correct" "$(echo $response | jq -r '.id')" "$launch_id"
        rlAssertEquals "Assert the name of launch is correct" "$(echo $response | jq -r '.name')" "$launch_name"
        rlAssertEquals "Assert the status of launch is correct" "$(echo $response | jq -r '.status')" "$launch_status"
        plan_summary=$(yq -r '.summary' plan.fmf)
        if [[ -z $ARTIFACTS ]]; then
                rlAssertEquals "Assert the description of launch is correct" "$(echo $response | jq -r '.description')" "$plan_summary"
        else
            if [[ $plan_summary == "null" ]]; then
            rlAssertEquals "Assert the description of launch is correct" "$(echo $response | jq -r '.description')" "$ARTIFACTS"
            else
            rlAssertEquals "Assert the description of launch is correct" "$(echo $response | jq -r '.description')" "$plan_summary, $ARTIFACTS"
            fi
        fi
        echo ""

        # Check all the launch attributes
        rl_message="Test attributes of the launch (context)"
        echo "$response" | jq -r ".attributes" > tmp_attributes.json && rlPass "$rl_message" || rlFail "$rl_message"
        length=$(yq -r ".context | length" plan.fmf)
        for ((item_index=0; item_index<$length; item_index++ )); do
            key=$(yq -r ".context | keys | .[$item_index]" plan.fmf)
            value=$(yq -r ".context.$key" plan.fmf)
            rlAssertGrep "$key" tmp_attributes.json -A1 > tmp_attributes_selection
            rlAssertGrep "$value" tmp_attributes_selection
        done
        rm tmp_attributes*

        for i in {1..10}; do
            echo ""
            test_name[$i]=${test[$i,'name']}
            test_name=${test_name[$i]}

            # Strip the '/test' prefix from the name cause the tests are saved
            # in `test.fmf` without this prefix.
            test_name=${test_name#/test}

            test_fullname=${test_fullname[$i]}
            test_uuid=${test_uuid[$i]}
            test_status[$i]=${test[$i,'status']}
            test_status=${test_status[$i]}

            # REST API | [GET] test-item-controller | uuid
            rlLogInfo "Get info about the test item $test_name"
            response=$(rest_api "$URL/api/v1/$PROJECT/item/uuid/$test_uuid")
            test_id=$(echo $response | jq -r '.id')
            rlAssertNotEquals "Assert the test id is not empty" "$test_id" ""
            rlAssertEquals "Assert the name is correct" "$(echo $response | jq -r '.name')" "$test_fullname"
            rlAssertEquals "Assert the status is correct" "$(echo $response | jq -r '.status')" "$test_status"
            test_description=$(yq -er ".\"$test_name\".summary" test.fmf) || test_description=''
            rlAssertEquals "Assert the description is correct" "$(echo $response | jq -r '.description // ""')" "$test_description"
            test_case_id=$(yq -r ".\"$test_name\".id" test.fmf)

            [[ $test_case_id != null ]] && rlAssertEquals "Assert the testCaseId is correct" "$(echo $response | jq -r '.testCaseId')" "$test_case_id"

            # Check the test attributes only for parent test items, do not check them for subresults
            if [[ ! "$test_name" =~ ^/subtest/ ]]; then
                # Check all the common test attributes/parameters
                for jq_element in attributes parameters; do
                    [[ $jq_element == attributes ]] && fmf_label="context"
                    [[ $jq_element == parameters ]] && fmf_label="environment"
                    rlLogInfo "Check the $jq_element for test $test_name ($fmf_label)"
                    echo "$response" | jq -r ".$jq_element" > tmp_attributes.json || rlFail "$jq_element listing into tmp_attributes.json"
                    length=$(yq -r ".$fmf_label | length" plan.fmf)
                    for ((item_index=0; item_index<$length; item_index++ )); do
                        key=$(yq -r ".$fmf_label | keys | .[$item_index]" plan.fmf)
                        value=$(yq -r ".$fmf_label.$key" plan.fmf)
                        rlAssertGrep "$key" tmp_attributes.json -A1 > tmp_attributes_selection
                        rlAssertGrep "$value" tmp_attributes_selection
                    done

                    # Check the rarities in the test attributes/parameters
                    if [[ $jq_element == attributes ]]; then
                        key="contact"
                        value="$(yq -r ".\"$test_name\".$key" test.fmf)"

                        if [[ $value != null ]]; then
                            # Get the contact items as values separated by a comma
                            value="$(yq -r '. | join(",")' <<< $value)"
                            rlAssertGrep "$key" tmp_attributes.json -A1 > tmp_attributes_selection

                            IFS=, read -r -a contact_items <<< "$value"
                            for contact_item in "${contact_items[@]}"; do
                                rlAssertGrep "$contact_item" tmp_attributes_selection
                            done
                        else
                            rlAssertNotGrep "$key" tmp_attributes.json
                        fi
                    elif [[ $jq_element == parameters ]]; then
                        key="TMT_TREE"
                        rlAssertNotGrep "$key" tmp_attributes.json
                    fi

                    rm tmp_attributes*
                done
            fi

            # REST API | [GET] log-controller | parent_id
            rlLogInfo "Get all logs from the test $test_name"
            response=$(rest_api "$URL/api/v1/$PROJECT/log/nested/$test_id")
            length=$(echo $response | jq -r ".content | length")
            level=("INFO" "ERROR")
            for ((content_index=0; content_index<$length; content_index++ )); do
                rlAssertEquals "Assert the level of the info log is correct" "$(echo $response | jq -r .content[$content_index].level)" "${level[$content_index]}"

                # Check the log message is correct (except the weird parent test)
                if [[ $i -ne 10 ]]; then
                    log_message=$(yq -r ".\"$test_name\".test" test.fmf | awk -F '"' '{print $2}' )
                    rlAssertEquals "Assert the message of the info log is correct" "$(echo $response | jq -r .content[$content_index].message)" "$log_message"
                fi
            done
        done

    rlPhaseEnd

    echo -e "\n\n\n::   PART 2\n"

    # Testing launch-per-plan mapping with launch-test structure
    rlPhaseStartTest "Extended Functionality - LAUNCH-PER-PLAN"
        launch_name=${PLAN_PREFIX}/launch-per-plan

        # TMT RUN
        rlLogInfo "A run that creates a launch per each plan and test items directly within"
        rlRun -s "tmt run --verbose --all report --how reportportal --launch-per-plan --launch '$launch_name' " 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id
        rlAssertNotGrep "suite:" $rlRun_LOG
        identify_tests   # >> $test_uuid[1..10], $test_fullname[1..10]

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")
        length=$(echo $response | jq -r ".content | length")
        for ((content_index=0; content_index<$length; content_index++ )); do
            parent_item_json=$(echo $response | jq -r .content[$content_index])
            parent_item_name=$(echo $parent_item_json | jq -r .name)

            if jq -e '.name == "/test/subresults"' <<< "$parent_item_json" > /dev/null; then
                # All parent tests with subresults must have child subresult items
                rlAssertEquals "Assert the item ($parent_item_name) has child items" "$(echo $parent_item_json | jq -r .hasChildren)" "true"
            else
                # Tests with no subresults must not have any child items
                rlAssertEquals "Assert the item ($parent_item_name) has no child items" "$(echo $parent_item_json | jq -r .hasChildren)" "false"
            fi
        done
    rlPhaseEnd

    # Testing suite-per-plan mapping with launch-suite-test structure
    rlPhaseStartTest "Extended Functionality - SUITE-PER-PLAN"
        launch_name=${PLAN_PREFIX}/suite-per-plan
        plan_summary=$(yq -r '.summary' plan.fmf)
        launch_description="Testing the integration of tmt and Report Portal via its API with suite-per-plan mapping"
        launch_status=$PLAN_STATUS
        suite_name=$PLAN_PREFIX

        # TMT RUN
        rlLogInfo "A run that creates a launch with a suite per each plan and test items within"
        rlRun -s "tmt run --verbose --all report --how reportportal --suite-per-plan --launch '$launch_name' --launch-description '$launch_description'" 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id
        identify_suite   # >> $suite_uuid, $suite_id
        identify_tests   # >> $test_uuid[1..10], $test_fullname[1..10]
        echo ""

        # REST API | [GET] launch-controller | uuid
        rlLogInfo "Get info about the launch"
        response=$(rest_api "$URL/api/v1/$PROJECT/launch/uuid/$launch_uuid")
        rlAssertEquals "Assert the URL ID of launch is correct" "$(echo $response | jq -r '.id')" "$launch_id"
        rlAssertEquals "Assert the name of launch is correct" "$(echo $response | jq -r '.name')" "$launch_name"
        rlAssertEquals "Assert the status of launch is correct" "$(echo $response | jq -r '.status')" "$launch_status"
        rlAssertEquals "Assert the description of launch is correct" "$(echo $response | jq -r .description)" "$launch_description"

        # Check all the launch attributes
        rl_message="Test attributes of the launch (context)"
        echo "$response" | jq -r ".attributes" > tmp_attributes.json && rlPass "$rl_message" || rlFail "$rl_message"
        length=$(yq -r ".context | length" plan.fmf)
        for ((item_index=0; item_index<$length; item_index++ )); do
            echo ""
            key=$(yq -r ".context | keys | .[$item_index]" plan.fmf)
            value=$(yq -r ".context.$key" plan.fmf)
            rlAssertGrep "$key" tmp_attributes.json -A1 > tmp_attributes_selection
            rlAssertGrep "$value" tmp_attributes_selection
        done
        rm tmp_attributes*
        echo ""

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")
        length=$(echo $response | jq -r ".content | length")
        for ((content_index=0; content_index<$length; content_index++ )); do
            echo ""

            parent_item_json=$(echo $response | jq -r .content[$content_index])
            parent_item_name=$(echo $parent_item_json | jq -r .name)

            if [[ $content_index -eq 0 ]]; then
                # Check the suite item
                rlAssertEquals "Assert the item is a suite" "$(echo $parent_item_json | jq -r .hasChildren)" "true"
                rlAssertEquals "Assert the name of suite item ${suite_name}" "$(echo $parent_item_json | jq -r .name)" "${suite_name}"
                rlAssertEquals "Assert the description of suite item ${suite_name}" "$(echo $parent_item_json | jq -r .description)" "${plan_summary}<br>${launch_description}"
            else
                if jq -e '.name == "/test/subresults"' <<< "$parent_item_json" > /dev/null; then
                    # All parent tests with subresults must have child subresult items
                    rlAssertEquals "Assert the item (${parent_item_name}) has child items" "$(echo $parent_item_json | jq -r .hasChildren)" "true"
                else
                    # Tests with no subresults must not have any child items
                    rlAssertEquals "Assert the item (${parent_item_name}) has no child items" "$(echo $parent_item_json | jq -r .hasChildren)" "false"
                fi
                rlAssertEquals "Assert the name of test item ${test_fullname[$content_index]}" "$(echo $parent_item_json | jq -r .name)" "${test_fullname[$content_index]}"
                rlAssertEquals "Assert the UUID of test item ${test_fullname[$content_index]}" "$(echo $parent_item_json | jq -r .uuid)" "${test_uuid[$content_index]}"
            fi
        done

    rlPhaseEnd


    # Testing the test history is aggregated correctly with/out unique parameters and case IDs
     rlPhaseStartTest "Extended Functionality - HISTORY AGGREGATION"
        launch_name=${PLAN_PREFIX}/history-aggregation

        # TMT RUN [0]
        rlLogInfo "Initial run that creates a launch for history"
        rlRun -s "tmt run --verbose --all report --how reportportal --suite-per-plan --launch '${launch_name}_1'" 2 "" 1>/dev/null
        for i in {1..10}; do
            echo ""
            test_fullname=${TEST_PREFIX}${test[$i,'name']}
            test_uuid=$(rlRun "grep -m$i -A1 'test:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
            rlAssertNotEquals "Assert the test$i UUID is not empty" "{$test_uuid}" ""

            # REST API | [GET] test-item-controller | uuid
            rlLogInfo "Get info about the test item $i"
            response=$(rest_api "$URL/api/v1/$PROJECT/item/uuid/$test_uuid")
            rlAssertEquals "Assert the name is correct" "$(echo $response | jq -r '.name')" "$test_fullname"
            launch1_test_id[$i]=$(echo $response | jq -r '.id')
            rlAssertNotEquals "Assert the test id is not empty" "$launch1_test_id[$i]" ""
        done
        echo ""

        # TMT RUN [1]
        rlLogInfo "A run that creates a launch with filtered environment variables (by default)"
        rlRun -s "tmt run --verbose --all report --how reportportal --suite-per-plan --launch '${launch_name}_2'" 2 "" 1>/dev/null
        for i in {1..10}; do
            echo ""
            test_name=${test[$i,'name']}
            test_fullname=${TEST_PREFIX}${test_name}
            test_uuid=$(rlRun "grep -m$i -A1 'test:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
            rlAssertNotEquals "Assert the test$i UUID is not empty" "{$test_uuid}" ""

            # REST API | [GET] test-item-controller | uuid
            rlLogInfo "Get info about the test item $i"
            response=$(rest_api "$URL/api/v1/$PROJECT/item/uuid/$test_uuid")
            rlAssertEquals "Assert the name is correct" "$(echo $response | jq -r '.name')" "$test_fullname"
            launch2_test_id[$i]=$(echo $response | jq -r '.id')
            rlAssertNotEquals "Assert the test id is not empty" "$launch2_test_id[$i]" ""

            # REST API | [GET] test-item-controller | history
            rlLogInfo "Verify the history is aggregated"
            response=$(rest_api "$URL/api/v1/$PROJECT/item/history?filter.eq.id=${launch2_test_id[$i]}&historyDepth=2")
            rlAssertEquals "Assert the previous item in history" "$(echo $response | jq -r .content[0].resources[1].id)" "${launch1_test_id[$i]}"
        done
        echo ""

        # TMT RUN [2]
        rlLogInfo "A run that creates a launch without filtering the environment variables that break history aggregation"
        rlRun -s "tmt run --verbose --all report --how reportportal --suite-per-plan --launch '${launch_name}_3' --exclude-variables ''" 2 "" 1>/dev/null
        for i in {1..10}; do
            echo ""
            test_name=${test[$i,'name']}
            test_fullname=${TEST_PREFIX}${test_name}
            test_uuid=$(rlRun "grep -m$i -A1 'test:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
            rlAssertNotEquals "Assert the test$i UUID is not empty" "{$test_uuid}" ""

            # REST API | [GET] test-item-controller | uuid
            response=$(rest_api "$URL/api/v1/$PROJECT/item/uuid/$test_uuid")
            rlAssertEquals "Assert the name is correct" "$(echo $response | jq -r '.name')" "$test_fullname"
            launch3_test_id[$i]=$(echo $response | jq -r '.id')
            rlAssertNotEquals "Assert the test id is not empty" "$launch3_test_id[$i]" ""
            test_case_id=$(yq -r ".\"$test_name\".id" test.fmf)
            [[ $test_case_id != null ]] && rlAssertEquals "Assert the test ${test_name} has a correct testCaseId" "$(echo $response | jq -r '.testCaseId')" "$test_case_id"
            echo "$response" | jq -r ".$jq_element" > tmp_attributes.json || rlFail "$jq_element listing into tmp_attributes.json"

            # FIXME: Ignore the check for subtests
            if [[ ! "$test_name" =~ ^/subtest/ ]]; then
                rlAssertGrep "TMT_TREE" tmp_attributes.json
            fi

            rm tmp_attributes*

            # history is not aggregated unless test case id is defined for given test (only test_2)
            [[ $i -eq 2 ]] && rlLogInfo "Verify the history should be aggregated" || rlLogInfo "Verify the history should not be aggregated"

            # REST API | [GET] test-item-controller | history
            response=$(rest_api "$URL/api/v1/$PROJECT/item/history?filter.eq.id=${launch3_test_id[$i]}&historyDepth=2")
            [[ $i -eq 2 ]] && rlAssertEquals "Assert the previous item is in history" "$(echo $response | jq -r .content[0].resources[1].id)" "${launch2_test_id[$i]}" \
                           || rlAssertNotEquals "Assert the previous item is not in history" "$(echo $response | jq -r .content[0].resources[1].id)" "${launch2_test_id[$i]}"
        done

    rlPhaseEnd


    # Testing integration with ReportPortal built-in RERUN feature with Retry items
    rlPhaseStartTest "Extended Functionality - NAME-BASED RERUN"
        launch_name=${PLAN_PREFIX}/name-based-rerun
        suite_name=$PLAN_PREFIX

        # TMT RUN [0]
        rlLogInfo "Initial run that creates a launch"
        rlRun -s "tmt run --verbose --all report --how reportportal --suite-per-plan --launch '$launch_name'" 2 "" 1>/dev/null
        for i in {1..10}; do
            core_test_uuid[$i]=$(rlRun "grep -m$i -A1 'test:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
            rlAssertNotEquals "Assert the test$i UUID is not empty" "{$core_test_uuid[$i]}" ""
        done
        echo ""

        # TMT RE-RUN [1]
        rlLogInfo "Create a new run that is reported as rerun within the last same-named launch"
        rlRun -s "tmt run --verbose --all report --how reportportal --suite-per-plan --launch '$launch_name' --launch-rerun" 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id
        identify_suite   # >> $suite_uuid
        identify_tests   # >> $test_uuid[1..10], $test_fullname[1..10]
        rlAssertGrep "suite: $suite_name" $rlRun_LOG

        # REST API | [GET] launch-controller | uuid
        rlLogInfo "Get info about the launch"
        response=$(rest_api "$URL/api/v1/$PROJECT/launch/uuid/$launch_uuid")
        rlAssertEquals "Assert the launch is rerun" "$(echo $response | jq -r '.rerun')" "true"

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")

        length=$(echo $response | jq -r ".content | length")
        for ((content_index=1; content_index<$length; content_index++ )); do
            i=$content_index
            rlAssertEquals "Assert the test item has correct UUID" "$(echo $response | jq -r .content[$content_index].uuid)" "${test_uuid[$i]}"
            rlAssertEquals "Assert the test item retry item has a correct UUID" "$(echo $response | jq -r .content[$content_index].retries[0].uuid)" "${core_test_uuid[$i]}"
        done
    rlPhaseEnd


    # Testing integration with tmt-stored UUIDs appending new logs to the same item
    rlPhaseStartTest "Extended Functionality - UUID-BASED RERUN"
        launch_name=${PLAN_PREFIX}/UUID-based-rerun
        suite_name=$PLAN_PREFIX

        # TMT RUN [0]
        rlLogInfo "Initial run that creates a launch"
        rlRun -s "tmt run --verbose --all report --how reportportal --suite-per-plan --launch '$launch_name'" 2 "" 1>/dev/null
        identify_tests   # >> $test_uuid[1..10], $test_fullname[1..10]
        echo ""

        # TMT RE-RUN [1]
        rlLogInfo "Execute and report the same run again to append new test logs"
        rlRun -s "tmt run --verbose --last --all execute --again report --how reportportal --suite-per-plan --launch '$launch_name' --again" 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")

        length=$(echo $response | jq -r ".content | length")
        for ((content_index=1; content_index<$length; content_index++ )); do
            i=$content_index
            rlAssertEquals "Assert the test item has correct UUID" "$(echo $response | jq -r .content[$content_index].uuid)" "${test_uuid[$i]}"
            test_id[$i]="$(echo $response | jq -r .content[$content_index].id)"
            rlAssertNotEquals "Assert the test$i id is not empty" "${test_id[$i]}" ""

            # REST API | [GET] log-controller | parent_id
            rlLogInfo "Get all logs from the test$i"
            response_log=$(rest_api "$URL/api/v1/$PROJECT/log/nested/${test_id[$i]}")
            test_name=${test[$i,'name']}
            length_log=$(echo $response_log | jq -r ".content | length")
            if [[ $i -eq 2 ]]; then
                level=("INFO" "INFO")
            else
                level=("INFO" "ERROR" "INFO" "ERROR")
            fi
            for ((content_index=0; content_index<$length_log; content_index++ )); do
                rlAssertEquals "Assert the level of the info log is correct" "$(echo $response_log | jq -r .content[$content_index].level)" "${level[$content_index]}"
                if [[ $i -ne 3 ]]; then
                    log_message=$(yq -r ".\"$test_name\".test" test.fmf | awk -F '"' '{print $2}' )
                    rlAssertEquals "Assert the message of the info log is correct" "$(echo $response_log | jq -r .content[$content_index].message)" "$log_message"
                fi
            done
        done
    rlPhaseEnd


    # Uploading empty report with IDLE states and updating it within the same tmt run
    rlPhaseStartTest "Extended Functionality - IDLE REPORT"
        launch_name=${PLAN_PREFIX}/idle_report
        suite_name=$PLAN_PREFIX

        # TMT RUN [0]
        rlLogInfo "Initial run that only creates an empty launch (with empty suite and empty test items within) with defect type 'Idle' (pre-defined in the project within 'To Investigate' category)"
        rlRun -s "tmt run discover report --verbose --how reportportal --suite-per-plan --launch '$launch_name' --defect-type 'IDLE'" 3  "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id
        identify_tests   # >> $test_uuid[1..10], $test_fullname[1..10]

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")
        length=$(echo $response | jq -r ".content | length")
        for ((content_index=1; content_index<$length; content_index++ )); do
            i=$content_index
            rlAssertEquals "Assert the defect type of test[$i] was defined" "$(echo $response | jq -r .content[$content_index].statistics.defects.to_investigate.total)" "1"
            rlAssertNotEquals "Assert the defect type of test[$i]is not the default one" "$(echo $response | jq -r '.content['$content_index'].statistics.defects.to_investigate | keys[0]')" "ti001"
        done
        echo ""

        # TMT RE-RUN [1]
        rlLogInfo "Execute the same run and update the results, redefine the defect type to default value"
        rlRun -s "tmt run --last --all report --verbose --how reportportal --suite-per-plan --launch '$launch_name' --again" 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")
        length=$(echo $response | jq -r ".content | length")
        for ((content_index=1; content_index<$length; content_index++ )); do
            i=$content_index
            rlAssertEquals "Assert the test[$i] item has correct UUID" "$(echo $response | jq -r .content[$content_index].uuid)" "${test_uuid[$i]}"
            test_id[$i]="$(echo $response | jq -r .content[$content_index].id)"
            rlAssertNotEquals "Assert the test[$i] id is not empty" "${test_id[$i]}" ""
            if [[ "$(echo $response | jq -r .content[$content_index].status)" == "FAILED" ]]; then
                rlAssertEquals "Assert the defect type of test[$i] is the default one" "$(echo $response | jq -r '.content['$content_index'].statistics.defects.to_investigate | keys[0]')" "ti001"
            fi
        done
    rlPhaseEnd


    # Uploading new suites and new tests to an existing launch
    rlPhaseStartTest "Extended Functionality - UPLOAD TO LAUNCH"
        launch_name=${PLAN_PREFIX}/upload-to-launch
        suite_name=$PLAN_PREFIX

        # TMT RUN [0]
        # FIXME: 7 tests within? - spis ne - opravit
        rlLogInfo "Initial run that creates a launch (with suite item and 7 test items within)"
        rlRun -s "tmt run --all report --verbose --how reportportal --suite-per-plan --launch '$launch_name'" 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id
        init_launch_uuid=$launch_uuid

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items (1)"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")
        rlAssertEquals "Assert launch contains suite and 7 test items" "$(echo $response | jq -r .page.totalElements)" "7"
        echo ""

        # TMT RUN [1]
        # FIXME: 7 tests  - spis ne - opravit
        rlLogInfo "Additional run for an upload (of a suite item with 7 test items) to the launch"
        rlRun -s "tmt run --all report --verbose --how reportportal --suite-per-plan --upload-to-launch '$launch_id'" 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id
        rlAssertEquals "Assert the launch UUID is the same as the initial one" "$init_launch_uuid" "$launch_uuid"

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items (2)"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")
        rlAssertEquals "Assert launch contains another suite and 7 test items" "$(echo $response | jq -r .page.totalElements)" "8"
        echo ""

        # TMT RUN [2]
        rlLogInfo "Additional run for an upload (of 7 test items) to the launch"
        rlRun -s "tmt run --all report --verbose --how reportportal --launch-per-plan --upload-to-launch '$launch_id'" 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id
        rlAssertEquals "Assert the launch UUID is the same as the initial one" "$init_launch_uuid" "$launch_uuid"

        # REST API | [GET] test-item-controller | launch_id
        rlLogInfo "Get info about all launch items (7)"
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id")
        rlAssertEquals "Assert launch contains another 7 test items" "$(echo $response | jq -r .page.totalElements)" "11"
    rlPhaseEnd


    # Uploading new tests to an existing suite
    rlPhaseStartTest "Extended Functionality - UPLOAD TO SUITE"
        launch_name=${PLAN_PREFIX}/upload-to-suite
        suite_name=$PLAN_PREFIX

        # TMT RUN [0]
        rlLogInfo "Initial run that creates a suite item (with 7 test items)"
        rlRun -s "tmt run --all report --verbose --how reportportal --suite-per-plan --launch '$launch_name'" 2 "" 1>/dev/null
        identify_launch  # >> $launch_uuid, $launch_id
        identify_suite   # >> $suite_uuid
        init_launch_uuid=$launch_uuid

        # REST API | [GET] test-item-controller | uuid
        rlLogInfo "Obtain 'suite id' for an additional upload."
        response=$(rest_api "$URL/api/v1/$PROJECT/item/uuid/$suite_uuid")
        rlAssertEquals "Assert the UUID of launch is correct" "$(echo $response | jq -r '.launchId')" "$launch_id"
        suite_id=$(echo $response | jq -r .id)
        rlAssertNotEquals "Assert the suite ID is not empty" "$suite_id" ""
        echo ""

        # TMT RUN [1]
        rlLogInfo "Additional run for an upload (of 3 test items) to the suite"
        rlRun -s "tmt run --all report --verbose --how reportportal --upload-to-suite '$suite_id'" 2 "" 1>/dev/null
        identify_launch
        rlAssertEquals "Assert the launch UUID is the same as the initial one" "$init_launch_uuid" "$launch_uuid"

        # REST API | [GET] test-item-controller | launch_id, parent_id
        rlLogInfo "Get info about all the suite items."
        response=$(rest_api "$URL/api/v1/$PROJECT/item?filter.eq.launchId=$launch_id&filter.eq.parentId=$suite_id")
        rlAssertEquals "Assert suite contains suite 6 test items" "$(echo $response | jq -r .page.totalElements)" "6"
    rlPhaseEnd


    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove run workdir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
