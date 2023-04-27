#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Prepare"
        rlRun -s "tmt -vv run --scratch --id $run discover provision prepare"

        rlRun "grep '^        queued: multihost on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^        queued: default-0 on client-1 (client) and client-2 (client)' $rlRun_LOG"
        rlRun "grep '^        queued: default-1 on server (server)' $rlRun_LOG"

        rlRun "grep '^        queue tick #0: multihost on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]         name: multihost' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]         name: multihost' $rlRun_LOG"
        rlRun "grep '^\\[server (server)\\]           name: multihost' $rlRun_LOG"

        rlRun "grep '^        queue tick #1: default-0 on client-1 (client) and client-2 (client)' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]         how: shell' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]         overview: 1 script found' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]         how: shell' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]         overview: 1 script found' $rlRun_LOG"

        rlRun "grep '^        queue tick #2: default-1 on server (server)' $rlRun_LOG"
        rlRun "grep '^        how: shell' $rlRun_LOG"
        rlRun "grep '^        guest: server' $rlRun_LOG"
        rlRun "grep '^        overview: 1 script found' $rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Execute"
        rlRun -s "tmt -vvv run --scratch --id $run discover provision execute finish"

        rlRun "grep 'summary: 7 tests executed' $rlRun_LOG"

        rlRun "grep '^        queued: server-setup on server (server)' $rlRun_LOG"
        rlRun "grep '^        queued: tests on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^        queued: teardown on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"

        rlRun "grep '^        queue tick #0: server-setup on server (server)' $rlRun_LOG"
        rlRun "grep '^                ..:..:.. pass /server-setup/tests/A (on server (server)) \\[1/1\\]' $rlRun_LOG"

        rlRun "egrep '^                out: TMT_GUEST_HOSTNAME=[a-zA-Z0-9\-]+' $rlRun_LOG"
        rlRun "grep  '^                out: TMT_GUEST_ROLE=server' $rlRun_LOG"

        rlRun "grep  '^        queue tick #1: tests on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep  '^\\[client-1 (client)\\]                 ..:..:.. pass /tests/tests/B (on client-1 (client)) \\[1/1\\]' $rlRun_LOG"
        rlRun "grep  '^\\[client-2 (client)\\]                 ..:..:.. pass /tests/tests/B (on client-2 (client)) \\[1/1\\]' $rlRun_LOG"
        rlRun "grep  '^\\[server (server)\\]                   ..:..:.. pass /tests/tests/B (on server (server)) \\[1/1\\]' $rlRun_LOG"

        rlRun "grep '^        queue tick #2: teardown on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^\\[server (server)\\]                   ..:..:.. pass /teardown/tests/C (on server (server)) \\[1/1\\]' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]                 ..:..:.. pass /teardown/tests/C (on client-1 (client)) \\[1/1\\]' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]                 ..:..:.. pass /teardown/tests/C (on client-2 (client)) \\[1/1\\]' $rlRun_LOG"

        client1_hostname="$(yq -r '."client-1" | .container' $run/plans/provision/guests.yaml)"
        client2_hostname="$(yq -r '."client-2" | .container' $run/plans/provision/guests.yaml)"
        server_hostname="$(yq -r '."server" | .container' $run/plans/provision/guests.yaml)"

        # Make sure all guests see roles and the corresponding guests
        rlRun "egrep '\\[client-1 \\(client\\)\\]                 out: TMT_ROLE_client=$client1_hostname $client2_hostname' $rlRun_LOG"
        rlRun "egrep '\\[client-1 \\(client\\)\\]                 out: TMT_ROLE_server=$server_hostname' $rlRun_LOG"
        rlRun "egrep '\\[client-2 \\(client\\)\\]                 out: TMT_ROLE_client=$client1_hostname $client2_hostname' $rlRun_LOG"
        rlRun "egrep '\\[client-2 \\(client\\)\\]                 out: TMT_ROLE_server=$server_hostname' $rlRun_LOG"
        rlRun "egrep '\\[server \\(server\\)\\]                   out: TMT_ROLE_client=$client1_hostname $client2_hostname' $rlRun_LOG"
        rlRun "egrep '\\[server \\(server\\)\\]                   out: TMT_ROLE_server=$server_hostname' $rlRun_LOG"

        # Make sure each guest is notified about its own hostname and role
        rlRun "egrep '^\\[client-1 \\(client\\)\\]                 out: TMT_GUEST_HOSTNAME=$client1_hostname' $rlRun_LOG"
        rlRun "egrep '^\\[client-1 \\(client\\)\\]                 out: TMT_GUEST_ROLE=client' $rlRun_LOG"
        rlRun "egrep '^\\[client-2 \\(client\\)\\]                 out: TMT_GUEST_HOSTNAME=$client2_hostname' $rlRun_LOG"
        rlRun "egrep '^\\[client-2 \\(client\\)\\]                 out: TMT_GUEST_ROLE=client' $rlRun_LOG"
        rlRun "egrep '^\\[server \\(server\\)\\]                   out: TMT_GUEST_HOSTNAME=$server_hostname' $rlRun_LOG"
        rlRun "egrep '^\\[server \\(server\\)\\]                   out: TMT_GUEST_ROLE=server' $rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
