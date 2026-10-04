#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
    rlPhaseEnd

    rlPhaseStartTest "Basic exit codes"
        tmt="tmt run -ar provision -h $PROVISION_HOW"
        rlRun "$tmt execute -h tmt -s true" 0 "Good test"
        rlRun "$tmt execute -h tmt -s false" 1 "Bad test"
        rlRun "$tmt execute -h tmt -s fooo" 2 "Weird test"
        rlRun "$tmt" 3 "No tests"
    rlPhaseEnd

    # Shell framework maps: exit 0 -> pass, exit 1 -> fail,
    # exit 2+ -> error.  If the transport corrupts exit codes
    # (e.g. remaps non-zero to 0) a failing test would look
    # like it passed.
    #
    # Codes with special meaning in shell/container/signal contexts:
    #   2   - first code outside the {0: pass, 1: fail} map
    #   7   - arbitrary mid-range value
    #   125 - podman: container failed to start
    #   126 - shell: command not executable
    #   127 - shell: command not found
    #   128 - signal exit base value
    #   137 - SIGKILL (128 + 9), common in OOM kills
    #   255 - ssh connection/auth failure
    rlPhaseStartTest "Exit code propagation through transport"
        for code in 2 7 125 126 127 128 137 255; do
            rlRun -s "tmt run --scratch -ar provision -h $PROVISION_HOW execute -dddvvv -h tmt -s 'exit $code'" 2 \
                "Exit $code is classified as error"
            rlAssertGrep "Command returned '$code'" "$rlRun_LOG"
        done
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
