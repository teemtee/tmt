#!/bin/bash

# Include Beaker environment
. /usr/share/beakerlib/beakerlib.sh || exit 1

PACKAGE="tmt"
EXAMPLES="/usr/share/doc/tmt/examples"

rlJournalStart
    rlPhaseStartSetup
        rlAssertRpm $PACKAGE
        rlRun "TmpDir=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $TmpDir"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "version"
        rlRun -s "tmt --version" 0 "Check version"
        rlAssertGrep "tmt version:" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "help"
        # Note tmt has different levels of '--help', and L1 > L2 > L3 > L4
        #
        #     ----     ------     ------          ------           ------
        #     #ID#     #L1        #L2             #L3              #L4
        #     ----     ------     ------          ------           ------
        #      1)  tmt --help run --help discover --help --how fmf --help
        #      2)  tmt        run --help discover --help --how fmf --help
        #      3)  tmt        run        discover --help --how fmf --help
        #      4)  tmt        run        discover        --how fmf --help
        #
        # where
        #      1) is the same as tmt --help
        #      2) is the same as tmt run --help
        #      3) is the same as tmt run discover --help
        rlRun -s "tmt --help" 0 "Check tmt --help"
        rlAssertGrep "Test Management Tool" "$rlRun_LOG"
        rlRun -s 'tmt run --help' 0 "Check tmt run --help"
        rlAssertGrep 'Run test steps' "$rlRun_LOG"
        rlRun -s 'tmt run discover --help' 0 "Check tmt run discover --help"
        rlAssertGrep 'Gather information about test cases to be executed' "$rlRun_LOG"

        rlRun -s "tmt --help run --help discover --help --how fmf --help" 0 "Check tmt --help"
        rlAssertGrep "Test Management Tool" "$rlRun_LOG"
        rlRun -s 'tmt run --help discover --help --how fmf --help' 0 "Check tmt run --help"
        rlAssertGrep 'Run test steps' "$rlRun_LOG"
        rlRun -s 'tmt run discover --help --how fmf --help' 0 "Check tmt run discover --help"
        rlAssertGrep 'Gather information about test cases to be executed' "$rlRun_LOG"
        rlRun -s 'tmt run discover --how fmf --help' 0 "Check tmt run discover --how fmf --help"
        rlAssertGrep 'Discover available tests from fmf metadata' "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "man"
        rlRun -s "man tmt" 0 "Check man page"
        rlAssertGrep "usage is straightforward" "$rlRun_LOG"
        rlAssertNotGrep "WARNING" "$rlRun_LOG"
        rlAssertNotGrep "ERROR" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "examples"
        rlRun -s "ls $EXAMPLES" 0 "Check examples"
        rlAssertGrep "mini" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $TmpDir" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
