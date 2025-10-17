#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlLogInfo "Testing Ansible inventory generation functionality"
    rlPhaseEnd

    tmt_command="tmt run -vv --scratch --id ${run} plan --name"

    planName="plan/default-layout"
    rlPhaseStartTest "Inventory generation with no layout (default layout)"
        rlLogInfo "Testing basic inventory generation with default layout and single guest"

        # Run the plan that provisions a single guest with default layout
        rlRun -s "${tmt_command} ${planName}" 0

        # Check that inventory file was generated
        inventory_file="$run/$planName/provision/inventory.yaml"
        if [ -n "$inventory_file" ] && rlAssertExists "$inventory_file" "Inventory file should exist"; then
            # Verify basic inventory structure with default layout
            rlRun "cat $inventory_file"
            rlRun "yq -e '.all' $inventory_file" 0 "Has 'all' group"
            rlRun "yq -e '.all.hosts' $inventory_file" 0 "Has 'hosts' section"
        else
            rlFail "Inventory file not found or doesn't exist at expected location"
        fi
    rlPhaseEnd

    planName="plan/comprehensive-inventory"
    rlPhaseStartTest "Comprehensive inventory features"
        rlLogInfo "Testing multiple inventory features together with layout provided"

        rlRun -s "${tmt_command} ${planName}" 0

        # Find and verify inventory exists
        inventory_file="$run/$planName/provision/inventory.yaml"
        if [ -n "$inventory_file" ] && rlAssertExists "$inventory_file" "Inventory file should exist"; then
            # Basic inventory structure validation
            rlRun "cat $inventory_file"
            rlRun "yq -e '.all' $inventory_file" 0 "Has 'all' group"
            rlRun "yq -e '.all.hosts' $inventory_file" 0 "Has 'hosts' section"

            # Host vars specified in metadata are added to 'all' group
            rlAssertEquals "Frontend host has custom variable" "value1" "$(yq -r '.all.hosts."frontend-1".custom_var' $inventory_file)"

            # TMT-provided ansible behavioral vars are added automatically
            rlRun "yq -e '.all.hosts.\"frontend-1\".ansible_host' $inventory_file" 0 "Host has ansible_host env var"
            rlRun "yq -e '.all.hosts.\"frontend-1\".ansible_connection' $inventory_file" 0 "Host has ansible_connection env var"
            rlRun "yq -e '.all.hosts.\"frontend-1\".ansible_user' $inventory_file" 0 "Host has ansible_user env var"
            rlRun "yq -e '.all.hosts.\"frontend-1\".ansible_port' $inventory_file" 0 "Host has ansible_port env var"

            # 'role' works to specify group when ansible.group is not provided
            rlRun "yq -e '.all.children.webservers.children.backend.hosts.\"backend-1\"' $inventory_file" 0 "Host in role group (backend)"

            # Hosts with no group are added to 'ungrouped' group
            rlRun "yq -e '.all.children.ungrouped.hosts.\"orphan-host\"' $inventory_file" 0 "Orphan host in ungrouped"

            # 'ansible.group' has precedence over 'role' key
            rlRun "yq -e '.all.children.webservers.children.frontend.hosts.\"frontend-1\"' $inventory_file" 0 "Host in ansible.group (frontend)"
            rlRun "yq -e '.all.children.webserver.hosts.\"frontend-1\"' $inventory_file" 1 "Host NOT in role group (webserver)"

            # Correct nested host group assignment
            rlRun "yq -e '.all.children.webservers.children.frontend' $inventory_file" 0 "Frontend group nested under webservers"
            rlRun "yq -e '.all.children.webservers.children.backend' $inventory_file" 0 "Backend group nested under webservers"

            # Automatic creation of group if it doesn't exist in layout
            # Debug: Show the actual inventory structure around auto-created group
            rlRun "yq -r '.all.children | keys' $inventory_file" 0 "Show all children groups"
            rlRun "yq -e '.all.children.\"auto-created\".hosts.\"auto-group-host\"' $inventory_file" 0 "Auto-created group exists"

            # Ansible tasks are executed on correct hosts based on group membership
            # This validates that TMT-generated inventory correctly drives Ansible task execution
            log_file="$run/log.txt"
            rlAssertExists $log_file "TMT log file should exist"

            # Group-specific targeting: Tasks execute only on intended group members
            rlAssertGrep "FRONTEND_TASK_EXECUTED on frontend-1" $log_file
            rlAssertNotGrep "FRONTEND_TASK_EXECUTED on backend-1" $log_file
            rlAssertNotGrep "FRONTEND_TASK_EXECUTED on orphan-host" $log_file

            # Nested group inheritance: Parent group tasks run on child group members
            rlAssertGrep "WEBSERVERS_TASK_EXECUTED on frontend-1" $log_file
            rlAssertGrep "WEBSERVERS_TASK_EXECUTED on backend-1" $log_file
            rlAssertNotGrep "WEBSERVERS_TASK_EXECUTED on orphan-host" $log_file

            # Ungrouped host handling: Hosts without explicit groups receive ungrouped tasks
            rlAssertGrep "UNGROUPED_TASK_EXECUTED on orphan-host" $log_file
            rlAssertNotGrep "UNGROUPED_TASK_EXECUTED on frontend-1" $log_file
            rlAssertNotGrep "UNGROUPED_TASK_EXECUTED on backend-1" $log_file

        else
            rlFail "Inventory file not found or doesn't exist at expected location"
        fi
    rlPhaseEnd

    planName="plan/default-groups"
    rlPhaseStartTest "Default groups normalization"
        rlLogInfo "Testing layout normalization with missing 'all' and 'ungrouped' groups"

        rlRun -s "${tmt_command} ${planName}" 0

        # Check that inventory file was generated
        inventory_file="$run/$planName/provision/inventory.yaml"
        if [ -n "$inventory_file" ] && rlAssertExists "$inventory_file" "should exist"; then
            rlRun "cat $inventory_file"

            # Verify 'all' group is present (even if not in layout)
            rlRun "yq -e '.all' $inventory_file" 0 "Has 'all' group"
            rlRun "yq -e '.all.hosts' $inventory_file" 0 "Has 'hosts' section in 'all'"

            # Verify 'ungrouped' group is present (even if not in layout)
            rlRun "yq -e '.all.children.ungrouped' $inventory_file" 0 "Has 'ungrouped' group"

            # Verify host without group ends up in 'ungrouped'
            rlRun "yq -e '.all.children.ungrouped.hosts.\"no-group-host\"' $inventory_file" 0 "Host without group in 'ungrouped'"

            # Verify host with custom group still works
            rlRun "yq -e '.all.children.\"custom-group\".hosts.\"custom-host\"' $inventory_file" 0 "Host with custom group works"

        else
            rlFail "Inventory file not found or doesn't exist at expected location"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd

rlJournalEnd
