#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

TOKEN=$TMT_REPORT_REPORTPORTAL_TOKEN
URL=$TMT_REPORT_REPORTPORTAL_URL
PROJECT="$(grep 'project' 'data/plan.fmf' | awk -F ': ' '{print $2}')"

# testing all the attributes/parameters under a label
# $1=rl_message, $2=response, $3=jq_element, $4=fmf_file, $5=fmf_label
check_attr_label() {
    [[ $1 ]] && local rl_message=$1
    [[ $2 ]] && local response=$2
    [[ $3 ]] && local jq_element=$3
    [[ $4 ]] && local fmf_file=$4
    [[ $5 ]] && local fmf_label=$5
    echo "$response" | jq -r ".$jq_element" > tmp_attributes.json && rlPass "$rl_message" || rlFail "$rl_message"
    awk -v label=$fmf_label '$0~label,/^$/ {if($0 && $0!=label){print $0}}' $fmf_file | while IFS= read -r line
        do
            key="$(echo "$line" | grep -o '[^ :]*' | head -1)"
            value="$(echo "$line" | grep -o '[^ :]*' | tail -1)"
            rlAssertGrep "$key" tmp_attributes.json -A1 > tmp_attributes_selection
            rlAssertGrep "$value" tmp_attributes_selection
        done
    rm tmp_attributes*
}

# testing one of the attributes/parameters under a specific key
# $1=rl_message, $2=response, $3=jq_element, $4=fmf_file, $5=fmf_key, $6=test_index, $7=inv_grep_key, $8=inv_grep_value
check_attr_key() {
    [[ $1 ]] && local rl_message=$1
    [[ $2 ]] && local response=$2
    [[ $3 ]] && local jq_element=$3
    [[ $4 ]] && local fmf_file=$4
    [[ $5 ]] && local fmf_key=$5
    [[ $6 ]] && local test_index=$6
    [[ $7 ]] && local inv_grep_key="Not"   || local inv_grep_key=""
    [[ $8 ]] && local inv_grep_value="Not" || local inv_grep_value=""
    echo "$response" | jq -r ".$jq_element" > tmp_attributes.json && rlPass "$rl_message" || rlFail "$rl_message"
    rlAssert${inv_grep_key}Grep "$fmf_key" tmp_attributes.json -A1 > tmp_attributes_selection
    if [[ -f $file && ! $inv_grep_value ]]; then
        value="$(grep $fmf_key $fmf_file | sed -n "$test_index p" | tr -s ' ' | grep -o '[^ :]*' | tail -1)"
        rlAssert${inv_grep_value}Grep "$value" tmp_attributes_selection
    fi
    rm tmp_attributes*
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run workdir"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run --id $run --verbose" 2
        cat  $rlRun_LOG
        rlAssertGrep "launch: /plan" $rlRun_LOG
        rlAssertGrep "test: /test/bad" $rlRun_LOG
        rlAssertGrep "test: /test/good" $rlRun_LOG
        rlAssertGrep "test: /test/weird" $rlRun_LOG
        rlAssertGrep "url: http.*redhat.com.ui/\#${PROJECT}/launches/all/[0-9]{4}" $rlRun_LOG -Eq
    rlPhaseEnd

    rlPhaseStartTest "Interface Test"
        launch_uuid=$(rlRun "grep -A1 'launch:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
        rlAssertNotEquals "Assert the launch uuid is not empty" "$launch_uuid" ""
        test1_uuid=$(rlRun "grep -m1 -A1 'test:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
        rlAssertNotEquals "Assert the test1 uuid is not empty" "$test1_uuid" ""
        test2_uuid=$(rlRun "grep -m2 -A1 'test:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
        rlAssertNotEquals "Assert the test2 uuid is not empty" "$test2_uuid" ""
        test3_uuid=$(rlRun "grep -m3 -A1 'test:' $rlRun_LOG | tail -n1 | awk '{print \$NF}' ")
        rlAssertNotEquals "Assert the test3 uuid is not empty" "$test3_uuid" ""
        launch_id=$(rlRun "grep 'url:' $rlRun_LOG | awk '{print \$NF}' | xargs basename")
        rlAssertNotEquals "Assert the launch id is not empty" "$launch_id" ""

        # LAUNCH - via API launch-controller /v1/{projectName}/launch/uuid/{launchId}
        rlLog "Testing a launch via API"
        response=$(curl -X GET "${URL}/api/v1/${PROJECT}/launch/uuid/${launch_uuid}" -H  "accept: */*" -H  "Authorization: bearer ${TOKEN}")
        rlAssertEquals "Assert the id of launch is correct (id from url)" "$(echo $response | jq -r '.id')" "$launch_id"
        rlAssertEquals "Assert the name of launch is correct" "$(echo $response | jq -r '.name')" "/plan"
        rlAssertEquals "Assert the status of launch is correct" "$(echo $response | jq -r '.status')" "FAILED"
        rlAssertEquals "Assert the description of launch is correct" "$(echo $response | jq -r '.description')" "$(grep 'summary' 'plan.fmf' | awk -F ': ' '{print $2}')"
        check_attr_label "Test attributes of the launch" "$response" "attributes" "plan.fmf" "context:"

        # TEST ITEMS - via API test-item-controller /v1/{projectName}/item/uuid/{itemId}
        rlLog "Testing test item for test1 via API"
        response=$(curl -X GET "${URL}/api/v1/${PROJECT}/item/uuid/${test1_uuid}" -H  "accept: */*" -H  "Authorization: bearer ${TOKEN}")
        test1_id=$(echo $response | jq -r '.id')
        rlAssertNotEquals "Assert the test id is not empty" "$test1_id" ""
        rlAssertEquals "Assert the name is correct" "$(echo $response | jq -r '.name')" "/test/bad"
        rlAssertEquals "Assert the status is correct" "$(echo $response | jq -r '.status')" "FAILED"
        rlAssertEquals "Assert the description is correct" "$(echo $response | jq -r '.description')" "$(grep 'summary' 'test.fmf' | sed -n "1 p" | awk -F ': ' '{print $2}')"
        check_attr_label "Test attributes" "$response" "attributes" "plan.fmf" "context:"
        check_attr_key "Test attributes - contains contact" "$response" "attributes" "test.fmf" "contact" 1
        check_attr_label "Test parameters" "$response" "parameters" "test.fmf" "environment:"
        check_attr_key "Test parameters - contains no tmt variables" "$response" "parameters" "" "TMT_TREE" 1 "AssertNotGrep"

        rlLog "Testing test item for test2 via API"
        response=$(curl -X GET "${URL}/api/v1/${PROJECT}/item/uuid/${test2_uuid}" -H  "accept: */*" -H  "Authorization: bearer ${TOKEN}")
        test2_id=$(echo $response | jq -r '.id')
        rlAssertNotEquals "Assert the test id is not empty" "$test2_id" ""
        rlAssertEquals "Assert the name is correct" "$(echo $response | jq -r '.name')" "/test/good"
        rlAssertEquals "Assert the status is correct" "$(echo $response | jq -r '.status')" "PASSED"
        rlAssertEquals "Assert the description is correct" "$(echo $response | jq -r '.description')" "$(grep 'summary' 'test.fmf' | sed -n "2 p" | awk -F ': ' '{print $2}')"
        rlAssertEquals "Assert the testCaseId is correct" "$(echo $response | jq -r '.testCaseId')" "$(grep 'id' 'test.fmf' | awk -F ': ' '{print $2}')"
        check_attr_key "Test atributes - contains contact" "$response" "attributes" "test.fmf" "contact" 2
        check_attr_key "Test attributes - does not contain a previous contact" "$response" "attributes" "test.fmf" "contact" 1 "" "AssertNotGrep"
        check_attr_label "Test parameters" "$response" "parameters" "test.fmf" "environment:"

        rlLog "Testing test item for test3 via API"
        response=$(curl -X GET "${URL}/api/v1/${PROJECT}/item/uuid/${test3_uuid}" -H  "accept: */*" -H  "Authorization: bearer ${TOKEN}")
        test3_id=$(echo $response | jq -r '.id')
        rlAssertNotEquals "Assert the test id is not empty" "$test3_id" ""
        rlAssertEquals "Assert the name is correct" "$(echo $response | jq -r '.name')" "/test/weird"
        rlAssertEquals "Assert the status is correct" "$(echo $response | jq -r '.status')" "FAILED"
        rlAssertEquals "Assert the description is correct" "$(echo $response | jq -r '.description')" "$(grep 'summary' 'test.fmf' | sed -n "3 p" | awk -F ': ' '{print $2}')"
        check_attr_key "Test attributes - contains no contact" "$response" "attributes" "test.fmf" "contact" 3 "AssertNotGrep" ""

        # LOGS - via API log-controller /v1/{projectName}/log/nested/{parentId}
        rlLog "Testing logs for test1 via API"
        response=$(curl -X GET "${URL}/api/v1/${PROJECT}/log/nested/${test1_id}" -H  "accept: */*" -H  "Authorization: bearer ${TOKEN}")
        rlAssertEquals "Assert the level of the log is correct" "$(echo $response | jq -r '.content[0].level')" "INFO"
        output="$(grep 'test:' 'test.fmf' | sed -n "1 p" | awk -F \" '{print $2}')"
        rlAssertEquals "Assert the message of the log is correct" "$(echo $response | jq -r '.content[0].message')" "$output"
        rlAssertEquals "Assert the level of the log is correct" "$(echo $response | jq -r '.content[1].level')" "ERROR"
        rlAssertEquals "Assert the message of the log is correct" "$(echo $response | jq -r '.content[1].message')" "$output"

        rlLog "Testing logs for test2 via API"
        response=$(curl -X GET "${URL}/api/v1/${PROJECT}/log/nested/${test2_id}" -H  "accept: */*" -H  "Authorization: bearer ${TOKEN}")
        rlAssertEquals "Assert the level of the log is correct" "$(echo $response | jq -r '.content[0].level')" "INFO"
        output="$(grep 'test:' 'test.fmf' | sed -n "2 p" | awk -F \" '{print $2}')"
        rlAssertEquals "Assert the message of the log is correct" "$(echo $response | jq -r '.content[0].message')" "$output"

        rlLog "Testing logs for test3 via API"
        response=$(curl -X GET "${URL}/api/v1/${PROJECT}/log/nested/${test3_id}" -H  "accept: */*" -H  "Authorization: bearer ${TOKEN}")
        rlAssertEquals "Assert the level of the log is correct" "$(echo $response | jq -r '.content[0].level')" "INFO"
        rlAssertEquals "Assert the level of the log is correct" "$(echo $response | jq -r '.content[1].level')" "ERROR"

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove run workdir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
