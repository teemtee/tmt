#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt plan export ." 0 "Export plan"
        rlAssertGrep "- name: /plan/basic" $rlRun_LOG
        rlAssertGrep "- name: /plan/context" $rlRun_LOG
        rlAssertGrep "- name: /plan/environment" $rlRun_LOG
        rlAssertGrep "- name: /plan/gate" $rlRun_LOG
        rlAssertGrep "discover:" $rlRun_LOG
        rlAssertGrep "execute:" $rlRun_LOG
        rlAssertNotGrep " _" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "tmt plan export /plan/basic"
        rlRun -s "tmt plan export /plan/basic" 0 "Export plan"
        rlAssertGrep "- name: /plan/basic" $rlRun_LOG
        rlAssertGrep "summary: Just basic keys." $rlRun_LOG
        rlAssertGrep "discover:" $rlRun_LOG
        rlAssertGrep "execute:" $rlRun_LOG
        rlAssertNotGrep " _" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "tmt plan export /plan/context"
        rlRun -s "tmt plan export /plan/context" 0 "Export plan"
        rlAssertGrep "- name: /plan/context" $rlRun_LOG
        rlAssertGrep "summary: Define context" $rlRun_LOG
        rlAssertGrep "discover:" $rlRun_LOG
        rlAssertGrep "execute:" $rlRun_LOG
        rlAssertGrep "context:" $rlRun_LOG
        rlAssertGrep "component: dash" $rlRun_LOG
        rlAssertNotGrep " _" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "tmt plan export /plan/environment"
        rlRun -s "tmt plan export /plan/environment" 0 "Export plan"
        rlAssertGrep "- name: /plan/environment" $rlRun_LOG
        rlAssertGrep "summary: Define environment" $rlRun_LOG
        rlAssertGrep "discover:" $rlRun_LOG
        rlAssertGrep "execute:" $rlRun_LOG
        rlAssertGrep "environment:" $rlRun_LOG
        rlAssertGrep "RELEASE: f35" $rlRun_LOG
        rlAssertNotGrep " _" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "tmt plan export /plan/gate"
        rlRun -s "tmt plan export /plan/gate" 0 "Export plan"
        rlAssertGrep "- name: /plan/gate" $rlRun_LOG
        rlAssertGrep "summary: Define gate" $rlRun_LOG
        rlAssertGrep "discover:" $rlRun_LOG
        rlAssertGrep "execute:" $rlRun_LOG
        rlAssertGrep "gate:" $rlRun_LOG
        rlAssertGrep "- merge-pull-request" $rlRun_LOG
        rlAssertGrep "- add-build-to-update" $rlRun_LOG
        rlAssertGrep "- add-build-to-compose" $rlRun_LOG
        rlAssertNotGrep " _" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Invalid format"
        rlRun -s "tmt plan export --how weird" 2

        if rlIsRHELLike "=8"; then
            # RHEL-8 and Centos stream 8 usually offer an older Click package that has slightly
            # different wording & quotes.
            rlAssertgrep "Error: Invalid value for \"-h\" / \"--how\": invalid choice: weird. (choose from dict, json, yaml)" $rlRun_LOG
        else
            rlAssertGrep "Error: Invalid value for '-h' / '--how': 'weird' is not one of 'dict', 'json', 'template', 'yaml'." $rlRun_LOG
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
