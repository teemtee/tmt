#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp -r $(git rev-parse --show-toplevel)/examples/plugins $tmp"
        rlRun "cp -a data $tmp"
        rlRun "pushd $tmp"

        # For local development this can run already in venv, do not use venv
        if rpm -qf $(command -v python3); then
            USE_VENV=true
            rlRun "python3 -m venv --system-site-package venv"
            # To get venv's entry_point properly
            tmt="python3 \$(which tmt)"
        else
            USE_VENV=false
            tmt=tmt
        fi
    rlPhaseEnd

    rlPhaseStartTest "Using entry_points"
        $USE_VENV && rlRun "source venv/bin/activate"

        # Plugins are not available before
        rlRun -s "$tmt run discover -h example --help" "2"
        rlAssertGrep "Unsupported discover method" "$rlRun_LOG"
        rlRun -s "$tmt run provision -h example --help" "2"
        rlAssertGrep "Unsupported provision method" "$rlRun_LOG"
        rlRun -s "$tmt -r data lint --enable-check C000 --enforce-check C000" "1"
        rlAssertGrep "fail\s*C000 fmf node failed schema validation" "$rlRun_LOG"
        rlAssertGrep "fail\s*C000 key \"path\" not recognized" "$rlRun_LOG"
        rlAssertGrep "fail\s*C000 value of \"how\" is not" "$rlRun_LOG"

        # Install them to entry_point and they work now
        rlRun "pip install ./plugins"
        rlRun "$tmt run discover -h example --help"
        rlRun "$tmt run provision -h example --help"
        rlRun -s "$tmt -r data lint --enable-check C000 --enforce-check C000"

        # Uninstall them
        rlRun "pip uninstall -y demo-plugins"

        $USE_VENV && rlRun "deactivate"
    rlPhaseEnd

    rlPhaseStartTest "Using TMT_PLUGINS"
        # Plugins are not available before
        rlRun -s "$tmt run discover -h example --help" "2"
        rlAssertGrep "Unsupported discover method" "$rlRun_LOG"
        rlRun -s "$tmt run provision -h example --help" "2"
        rlAssertGrep "Unsupported provision method" "$rlRun_LOG"

        # Export variable and plugins work now
        rlRun "export TMT_PLUGINS=./plugins/example"
        rlRun "$tmt run discover -h example --help"
        rlRun "$tmt run provision -h example --help"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
