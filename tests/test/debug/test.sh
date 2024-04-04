#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd $tmp"
        rlRun "tmt init"
        rlRun "tmt plan create --template base /plan"
        rlRun "tmt test create --template shell /test"
    rlPhaseEnd

    rlPhaseStartTest "Test $PROVISION_HOW"
        # Run until execute
        tmt="tmt run --id $run --verbose"
        rlRun "$tmt --all --scratch --before execute provision -h $PROVISION_HOW"

        # Failing test
        rlRun "echo -e '#!/bin/bash\n/bin/false' > test/test.sh"
        rlRun "$tmt discover --force execute --force" 1 "Failing test"

        # Fixed test
        rlRun "echo -e '#!/bin/bash\n/bin/true' > test/test.sh"
        rlRun "$tmt discover --force execute --force" 0 "Fixed test"

        # Cleanup until finish
        rlRun "$tmt --until finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp $run" 0 "Remove tmp & run directory"
    rlPhaseEnd
rlJournalEnd
