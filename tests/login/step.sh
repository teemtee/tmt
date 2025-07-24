#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "tmt='tmt run -ar provision -h local'"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init -t mini"
    rlPhaseEnd

    rlPhaseStartTest "No login"
        rlRun -s "$tmt"
        rlAssertNotGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Last step"
        rlRun -s "$tmt login -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    finish$' -A4 '$rlRun_LOG' | grep -i interactive"
    rlPhaseEnd

    for step in discover provision prepare execute report finish; do
        rlPhaseStartTest "Selected step ($step)"
            rlRun -s "$tmt login -c true -s $step"

            if [ "$step" = "provision" ]; then
                rlRun "grep '^    $step$' -A13 '$rlRun_LOG' | grep -i interactive"
            elif [ "$step" = "prepare" ]; then
                rlRun "grep '^    $step$' -A17 '$rlRun_LOG' | grep -i interactive"
            elif [ "$step" = "execute" ]; then
                rlRun "grep '^    $step$' -A9 '$rlRun_LOG' | grep -i interactive"
            elif [ "$step" = "discover" ]; then
                rlRun "grep '^    $step$' -A9 '$rlRun_LOG' | grep -i 'No guests ready for login'"
            else
                rlRun "grep '^    $step$' -A5 '$rlRun_LOG' | grep -i interactive"
            fi
        rlPhaseEnd
    done

    rlPhaseStartTest "Failed command"
        rlRun -s "$tmt login -c false"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Last run"
        rlRun "tmt run -a provision -h local"
        rlRun -s "tmt run -rl login -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Last run failed"
        rlRun "tmt run provision -h local prepare --how shell --script false" 2
        rlRun -s "tmt run -rl login -c true" 2
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
