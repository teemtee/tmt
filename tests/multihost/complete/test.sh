#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

function check_current_topology () {
    topology_file=$1
    name=$2
    role=$3
    hostname=$4

    rlAssertEquals "Current guest name"     "$name"     "$(yq -r '.guest.name' $topology_file)"
    rlAssertEquals "Current guest role"     "$role"     "$(yq -r '.guest.role' $topology_file)"
    rlAssertEquals "Current guest hostname" "$hostname" "$(yq -r '.guest.hostname' $topology_file)"
}

function check_shared_topology () {
    rlAssertEquals "Guest names"        "client-1 client-2 server" "$(yq -r '."guest-names" | sort | join(" ")' $1)"
    rlAssertEquals "Role names"         "client server"            "$(yq -r '."role-names" | sort | join(" ")' $1)"
    rlAssertEquals "Client role guests" "client-1 client-2"        "$(yq -r '.roles.client | sort | join(" ")' $1)"
    rlAssertEquals "Server role guests" "server"                   "$(yq -r '.roles.server | sort | join(" ")' $1)"

    rlAssertEquals "Guest client-1 name"     "client-1"          "$(yq -r '.guests["client-1"].name' $1)"
    rlAssertEquals "Guest client-1 role"     "client"            "$(yq -r '.guests["client-1"].role' $1)"
    rlAssertEquals "Guest client-1 hostname" "$client1_hostname" "$(yq -r '.guests["client-1"].hostname' $1)"

    rlAssertEquals "Guest client-2 name"     "client-2"          "$(yq -r '.guests["client-2"].name' $1)"
    rlAssertEquals "Guest client-2 role"     "client"            "$(yq -r '.guests["client-2"].role' $1)"
    rlAssertEquals "Guest client-2 hostname" "$client2_hostname" "$(yq -r '.guests["client-2"].hostname' $1)"

    rlAssertEquals "Guest server name"     "server"              "$(yq -r '.guests["server"].name' $1)"
    rlAssertEquals "Guest server role"     "server"              "$(yq -r '.guests["server"].role' $1)"
    rlAssertEquals "Guest server hostname" "$server_hostname"    "$(yq -r '.guests["server"].hostname' $1)"
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Prepare"
        rlRun -s "tmt -vvv run --scratch --id $run discover provision prepare"

        rlRun "grep '^        queued prepare task #1: default-0 on client-1 (client) and client-2 (client)' $rlRun_LOG"
        rlRun "grep '^        queued prepare task #2: default-1 on server (server)' $rlRun_LOG"

        rlRun "grep '^        prepare task #1: default-0 on client-1 (client) and client-2 (client)' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]         how: shell' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]         overview: 3 scripts found' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]         how: shell' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]         overview: 3 scripts found' $rlRun_LOG"

        rlRun "grep '^        prepare task #2: default-1 on server (server)' $rlRun_LOG"
        rlRun "grep '^        how: shell' $rlRun_LOG"
        rlRun "grep '^        guest: server' $rlRun_LOG"
        rlRun "grep '^        overview: 3 scripts found' $rlRun_LOG"

        client1_hostname="$(yq -r '."client-1" | .container' $run/plans/provision/guests.yaml)"
        client2_hostname="$(yq -r '."client-2" | .container' $run/plans/provision/guests.yaml)"
        server_hostname="$(yq -r '."server" | .container' $run/plans/provision/guests.yaml)"

        rlRun "client1_topology_yaml=$(grep -Po '(?<=^\[client-1 \(client\)\]             out: TMT_TOPOLOGY_YAML=).*' $rlRun_LOG)"
        rlRun "client2_topology_yaml=$(grep -Po '(?<=^\[client-2 \(client\)\]             out: TMT_TOPOLOGY_YAML=).*' $rlRun_LOG)"
        rlRun "server_topology_yaml=$(grep -Po '(?<=^            out: TMT_TOPOLOGY_YAML=).*' $rlRun_LOG)"

        rlRun "client1_topology_sh=$(grep -Po '(?<=^\[client-1 \(client\)\]             out: TMT_TOPOLOGY_BASH=).*' $rlRun_LOG)"
        rlRun "client2_topology_sh=$(grep -Po '(?<=^\[client-2 \(client\)\]             out: TMT_TOPOLOGY_BASH=).*' $rlRun_LOG)"
        rlRun "server_topology_sh=$(grep -Po '(?<=^            out: TMT_TOPOLOGY_BASH=).*' $rlRun_LOG)"

        check_current_topology "$client1_topology_yaml" "client-1" "client" "$client1_hostname"
        check_current_topology "$client2_topology_yaml" "client-2" "client" "$client2_hostname"
        check_current_topology "$server_topology_yaml"  "server"   "server" "$server_hostname"
        check_shared_topology "$client1_topology_yaml"
        check_shared_topology "$client2_topology_yaml"
        check_shared_topology "$server_topology_yaml"
    rlPhaseEnd

    rlPhaseStartTest "Execute"
        rlRun -s "tmt -vvv run --scratch --id $run discover provision execute finish"

        rlRun "grep 'summary: 7 tests executed' $rlRun_LOG"

        rlRun "grep '^        queued execute task #1: server-setup on server (server)' $rlRun_LOG"
        rlRun "grep '^        queued execute task #2: tests on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^        queued execute task #3: teardown on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"

        rlRun "grep '^        execute task #1: server-setup on server (server)' $rlRun_LOG"
        rlRun "grep '^                ..:..:.. pass /server-setup/tests/A (on server (server)) \\[1/1\\]' $rlRun_LOG"

        rlRun "grep  '^        execute task #2: tests on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep  '^\\[client-1 (client)\\]                 ..:..:.. pass /tests/tests/B (on client-1 (client)) \\[1/1\\]' $rlRun_LOG"
        rlRun "grep  '^\\[client-2 (client)\\]                 ..:..:.. pass /tests/tests/B (on client-2 (client)) \\[1/1\\]' $rlRun_LOG"
        rlRun "grep  '^\\[server (server)\\]                   ..:..:.. pass /tests/tests/B (on server (server)) \\[1/1\\]' $rlRun_LOG"

        rlRun "grep '^        execute task #3: teardown on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^\\[server (server)\\]                   ..:..:.. pass /teardown/tests/C (on server (server)) \\[1/1\\]' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]                 ..:..:.. pass /teardown/tests/C (on client-1 (client)) \\[1/1\\]' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]                 ..:..:.. pass /teardown/tests/C (on client-2 (client)) \\[1/1\\]' $rlRun_LOG"

        client1_hostname="$(yq -r '."client-1" | .container' $run/plans/provision/guests.yaml)"
        client2_hostname="$(yq -r '."client-2" | .container' $run/plans/provision/guests.yaml)"
        server_hostname="$(yq -r '."server" | .container' $run/plans/provision/guests.yaml)"

        rlRun "client1_topology_yaml=$(grep -Po '(?<=^\[client-1 \(client\)\]                 out: TMT_TOPOLOGY_YAML=).*B-2.*' $rlRun_LOG)"
        rlRun "client2_topology_yaml=$(grep -Po '(?<=^\[client-2 \(client\)\]                 out: TMT_TOPOLOGY_YAML=).*B-2.*' $rlRun_LOG)"
        rlRun "server_topology_yaml=$(grep -Po '(?<=^\[server \(server\)\]                   out: TMT_TOPOLOGY_YAML=).*B-2.*' $rlRun_LOG)"

        rlRun "client1_topology_sh=$(grep -Po '(?<=^\[client-1 \(client\)\]                 out: TMT_TOPOLOGY_BASH=).*B-2.*' $rlRun_LOG)"
        rlRun "client2_topology_sh=$(grep -Po '(?<=^\[client-2 \(client\)\]                 out: TMT_TOPOLOGY_BASH=).*B-2.*' $rlRun_LOG)"
        rlRun "server_topology_sh=$(grep -Po '(?<=^\[server \(server\)\]                   out: TMT_TOPOLOGY_BASH=).*B-2.*' $rlRun_LOG)"

        check_current_topology "$client1_topology_yaml" "client-1" "client" "$client1_hostname"
        check_current_topology "$client2_topology_yaml" "client-2" "client" "$client2_hostname"
        check_current_topology "$server_topology_yaml"  "server"   "server" "$server_hostname"
        check_shared_topology "$client1_topology_yaml"
        check_shared_topology "$client2_topology_yaml"
        check_shared_topology "$server_topology_yaml"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
