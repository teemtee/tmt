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
        rlRun -s "tmt -vv run --scratch --id $run discover provision execute"

        rlRun "grep '^        queued: server-setup on server (server)' $rlRun_LOG"
        rlRun "grep '^        queued: tests on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^        queued: teardown on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"

        rlRun "grep '^        queue tick #0: server-setup on server (server)' $rlRun_LOG"
        rlRun "grep '^                00:00:00 pass /server-setup/tests/A \\[1/1\\]' $rlRun_LOG"

        rlRun "grep '^        queue tick #1: tests on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]                 ..:..:.. pass /tests/tests/B \\[1/1\\]' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]                 ..:..:.. pass /tests/tests/B \\[1/1\\]' $rlRun_LOG"
        rlRun "grep '^\\[server (server)\\]                   ..:..:.. pass /tests/tests/B \\[1/1\\]' $rlRun_LOG"

        rlRun "grep '^        queue tick #2: teardown on client-1 (client), client-2 (client) and server (server)' $rlRun_LOG"
        rlRun "grep '^\\[server (server)\\]                   00:00:00 pass /teardown/tests/C \\[1/1\\]' $rlRun_LOG"
        rlRun "grep '^\\[client-1 (client)\\]                 00:00:00 pass /teardown/tests/C \\[1/1\\]' $rlRun_LOG"
        rlRun "grep '^\\[client-2 (client)\\]                 00:00:00 pass /teardown/tests/C \\[1/1\\]' $rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
