#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

TOKEN=$TMT_REPORT_REPORTPORTAL_TOKEN
URL=$TMT_REPORT_REPORTPORTAL_URL
PROJECT="$(yq -r .report.project 'data/plan.fmf')"


rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run workdir"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run --id $run --verbose" 2
        rlAssertGrep "launch: /plan" $rlRun_LOG
        rlAssertGrep "test: /test/bad" $rlRun_LOG
        rlAssertGrep "test: /test/good" $rlRun_LOG
        rlAssertGrep "test: /test/weird" $rlRun_LOG
        rlAssertGrep "url: http.*redhat.com.ui/#${PROJECT}/launches/all/[0-9]{4}" $rlRun_LOG -Eq
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
        response=$(curl -X GET "$URL/api/v1/$PROJECT/launch/uuid/$launch_uuid" -H  "accept: */*" -H  "Authorization: bearer $TOKEN")
        rlAssertEquals "Assert the id of launch is correct (id from url)" "$(echo $response | jq -r '.id')" "$launch_id"
        rlAssertEquals "Assert the name of launch is correct" "$(echo $response | jq -r '.name')" "/plan"
        rlAssertEquals "Assert the status of launch is correct" "$(echo $response | jq -r '.status')" "FAILED"
        rlAssertEquals "Assert the description of launch is correct" "$(echo $response | jq -r '.description')" "$(yq -r '.summary' plan.fmf)"

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


        # TEST ITEMS - via API test-item-controller /v1/{projectName}/item/uuid/{itemId}
        declare -A test=([1,'uuid']=$test1_uuid [1,'name']='bad'   [1,'status']='FAILED'
                         [2,'uuid']=$test2_uuid [2,'name']='good'  [2,'status']='PASSED'
                         [3,'uuid']=$test3_uuid [3,'name']='weird' [3,'status']='FAILED')

        for test_index in {1..3}; do
            test_uuid=${test[$test_index,'uuid']}
            test_name=${test[$test_index,'name']}
            test_status=${test[$test_index,'status']}

            rlLog "Testing test item for test /$test_name via API"
            response=$(curl -X GET "$URL/api/v1/$PROJECT/item/uuid/$test_uuid" -H  "accept: */*" -H  "Authorization: bearer $TOKEN")
            test_id=$(echo $response | jq -r '.id')
            rlAssertNotEquals "Assert the test id is not empty" "$test_id" ""
            rlAssertEquals "Assert the name is correct" "$(echo $response | jq -r '.name')" "/test/$test_name"
            rlAssertEquals "Assert the status is correct" "$(echo $response | jq -r '.status')" "$test_status"
            test_description=$(yq -r ".\"/$test_name\".summary" test.fmf)
            rlAssertEquals "Assert the description is correct" "$(echo $response | jq -r '.description')" "$test_description"
            test_case_id=$(yq -r ".\"/$test_name\".id" test.fmf)
            [[ $test_case_id != null ]] && rlAssertEquals "Assert the testCaseId is correct" "$(echo $response | jq -r '.testCaseId')" "$test_case_id"

            for jq_element in attributes parameters; do

                # Check all the common test attributes/parameters
                [[ $jq_element == attributes ]] && fmf_label="context"
                [[ $jq_element == parameters ]] && fmf_label="environment"
                rlLogInfo "Check the $jq_element for test /$test_name ($fmf_label)"
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
                    value="$(yq -r ".\"/$test_name\".$key" test.fmf)"
                    if [[ $value != null ]]; then
                        rlAssertGrep "$key" tmp_attributes.json -A1 > tmp_attributes_selection
                        rlAssertGrep "$value" tmp_attributes_selection
                    else
                        rlAssertNotGrep "$key" tmp_attributes.json
                    fi
                elif [[ $jq_element == parameters ]]; then
                    key="TMT_TREE"
                    rlAssertNotGrep "$key" tmp_attributes.json
                fi

                rm tmp_attributes*
            done

            # Check the logs - via API log-controller /v1/{projectName}/log/nested/{parentId}
            rlLogInfo "Check the logs for test /$test_name via API"
            response=$(curl -X GET "$URL/api/v1/$PROJECT/log/nested/$test_id" -H  "accept: */*" -H  "Authorization: bearer $TOKEN")
            length=$(echo $response | jq -r ".content | length")
            echo "length: $length"
            level=("INFO" "ERROR")
            for ((content_index=0; content_index<$length; content_index++ )); do
                rlAssertEquals "Assert the level of the info log is correct" "$(echo $response | jq -r .content[$content_index].level)" "${level[$content_index]}"
                if [[ $test_name != weird ]]; then
                    log_message=$(yq -r ".\"/$test_name\".test" test.fmf | awk -F '"' '{print $2}' )
                    rlAssertEquals "Assert the message of the info log is correct" "$(echo $response | jq -r .content[$content_index].message)" "$log_message"
                fi
            done
        done

    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove run workdir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
