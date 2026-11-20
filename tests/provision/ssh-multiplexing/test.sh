#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"

        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "long_run=\$(mktemp -d /tmp/tmp.veryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryverylongXXX)" 0 "Create run directory with a very long name"
        rlRun "failed_run=\$(mktemp -d /tmp/tmp.veryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryverylongXXX)" 0 "Create run directory for fallback failure"

        rlRun "tmpdir=\$(mktemp -d)" 0 "Create temporary directory"
        rlRun "sed 's|RUN|$run|g' test.exp > $tmpdir/test.exp"
        rlRun "chmod a+x $tmpdir/test.exp"

        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "SSH multiplexing should be enabled by default ($PROVISION_HOW)"
        rlRun "tmt -vv run -i $run -a provision -h $PROVISION_HOW"
        rlAssertGrep "Spawning the SSH master process" "$run/log.txt"
        rlAssertGrep "Master running (pid=" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartTest "SSH multiplexing should use a short directory for long workdirs ($PROVISION_HOW)"
        rlRun "tmt -vv run -i $long_run -a provision -h $PROVISION_HOW"
        rlAssertNotGrep "SSH multiplexing will not be used" "$long_run/log.txt"
        rlAssertGrep "SSH master socket path will be '.*' (temporary directory)." "$long_run/log.txt"
        rlAssertGrep "Master running (pid=" "$long_run/log.txt"

        # Each temporary socket directory must be removed when its master exits.
        while read -r socket; do
            rlRun "test ! -d '${socket%/*}'" 0 "Remove temporary socket directory"
        done < <(sed -n "s/.*SSH master socket path will be '\([^']*\)' (temporary directory).*/\1/p" "$long_run/log.txt" | sort -u)
    rlPhaseEnd

    rlPhaseStartTest "SSH multiplexing should be disabled if no short directory is available ($PROVISION_HOW)"
        rlRun "python3 ../socket-directory-unavailable.py -vv run -i $failed_run -a provision -h $PROVISION_HOW"
        rlAssertGrep "No usable temporary SSH socket directory could be created." "$failed_run/log.txt"
        rlAssertNotGrep "Spawning the SSH master process:" "$failed_run/log.txt"
        rlAssertGrep "The SSH master process cannot be terminated because it is disabled." "$failed_run/log.txt"
    rlPhaseEnd

    if [ "$PROVISION_HOW" = "virtual" ]; then
        rlPhaseStartTest "Make sure SSH multiplexing does not block reuse of guests (#3520)"
            rlRun "tmt -vv run -i $run --scratch provision -h $PROVISION_HOW"

            rlRun "pgrep --full 'ssh .* -i $run/plan/provision/default-0/id_ecdsa'" 1 "Check whether the SSH master process is still running"

            rlRun -s "$tmpdir/test.exp"
            rlAssertGrep "Starting interactive shell" $rlRun_LOG
            rlAssertGrep "Interactive shell finished" $rlRun_LOG

            rlRun "tmt -vv run -i $run finish"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmpdir" 0 "Remove temporary directory"
        rlRun "rm -r $run" 0 "Remove run directory"
        rlRun "rm -r $long_run" 0 "Remove run directory with the long name"
        rlRun "rm -r $failed_run" 0 "Remove fallback failure run directory"
    rlPhaseEnd
rlJournalEnd
