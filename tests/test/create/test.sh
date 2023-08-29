#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    DIR_DOT_SYNTAX="some/nice/dir/structure"
    TEST_STRING="# this is a testing comment"
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "mkdir -p $DIR_DOT_SYNTAX"
        rlRun "set -o pipefail"
        rlRun "tmt init"
    rlPhaseEnd

    rlPhaseStartTest "Shell template"
        rlRun "tmt test create test_shell --template shell"
        rlAssertExists "$tmp/test_shell/main.fmf"
        rlAssertExists "$tmp/test_shell/test.sh"
    rlPhaseEnd

    rlPhaseStartTest "Existing directory and files"
        rlRun -s "tmt test create test_shell --template shell" \
            2 "test already exists"
        rlAssertGrep "File '$tmp/test_shell/main.fmf' already exists." \
            "${rlRun_LOG}"
        rlAssertGrep "Test directory '$tmp/test_shell' already exists." \
            "${rlRun_LOG}"
        rlAssertExists "$tmp/test_shell/main.fmf"
        rlAssertExists "$tmp/test_shell/test.sh"
    rlPhaseEnd

    rlPhaseStartTest "BeakerLib template"
        rlRun "tmt test create test_beakerlib --template beakerlib"
        rlAssertExists "$tmp/test_beakerlib/main.fmf"
        rlAssertExists "$tmp/test_beakerlib/test.sh"
    rlPhaseEnd

    rlPhaseStartTest "non-existent template"
        rlRun -s "tmt test create non-existent --template non-existent" \
            2 "Template doesn't exist"
        rlAssertGrep "Invalid template 'non-existent'." "${rlRun_LOG}"
    rlPhaseEnd

    rlPhaseStartTest "Using the '.' syntax"
        rlRun "cd $DIR_DOT_SYNTAX"
        rlRun "tmt test create . --template shell"
        rlAssertExists "$tmp/$DIR_DOT_SYNTAX/main.fmf"
        rlAssertExists "$tmp/$DIR_DOT_SYNTAX/test.sh"
    rlPhaseEnd

    rlPhaseStartTest "Using the --dry option"
        rlRun -s "tmt test create -n -t beakerlib example-test"
        rlAssertGrep "Test directory .* would be created." "${rlRun_LOG}"
        rlAssertGrep "Test metadata .* would be created." "${rlRun_LOG}"
        rlAssertGrep "Test script .* would be created." "${rlRun_LOG}"
        rlAssertNotExists "$tmp/example-test"
        rlAssertNotExists "$tmp/example-test/main.fmf"
        rlAssertNotExists "$tmp/example-test/test.sh"

        rlRun -s "tmt test create -t beakerlib example-test"
        rlRun "echo '$TEST_STRING' >> $tmp/example-test/test.sh" \
            0 "Inserting testing comment into the test.sh"
        rlRun -s "tmt test create -n -t beakerlib example-test" \
            2 "Test already exists"
        rlRun "grep '$TEST_STRING' $tmp/example-test/test.sh" \
            0 "Check testing comment was not overwritten"

        rlRun -s "tmt test create -nf -t beakerlib example-test"
        rlAssertGrep "Test directory .* already exists." "${rlRun_LOG}"
        rlAssertGrep "Test metadata .* would be overwritten." "${rlRun_LOG}"
        rlAssertGrep "Test script .* would be overwritten." "${rlRun_LOG}"
        rlRun "grep '$TEST_STRING' $tmp/example-test/test.sh" \
            0 "Check testing comment was not overwritten"
    rlPhaseEnd

    rlPhaseStartTest "Using the --link option"
        default_relation="relates"
        relation_taget_01="RT01"
        relation_taget_02="https://foo.redhat.com/RT02"
        relation_taget_03="verifies:https://foo.redhat.com/RT03"

        rlRun "rm -rf $tmp/test_link" "0-255"
        rlRun "tmt test create test_link --template shell"
        rlAssertExists "$tmp/test_link/main.fmf"
        rlAssertNotGrep "^link:" "$tmp/test_link/main.fmf"

        rlRun "rm -rf $tmp/test_link" "0-255"
        rlRun -s "tmt test create test_link --template shell --link ''" "1-255"
        rlAssertNotExists "$tmp/test_link/main.fmf"
        rlAssertGrep "Invalid spec" "${rlRun_LOG}"

        rlRun "rm -rf $tmp/test_link" "0-255"
        rlRun "tmt test create test_link --template shell --link $relation_taget_01"
        rlAssertExists "$tmp/test_link/main.fmf"
        rlRun -s "yq -ry .link[0] $tmp/test_link/main.fmf"
        rlAssertGrep "$default_relation: $relation_taget_01" "${rlRun_LOG}"

        rlRun "rm -rf $tmp/test_link" "0-255"
        rlRun "tmt test create test_link --template shell --link $relation_taget_02"
        rlAssertExists "$tmp/test_link/main.fmf"
        rlRun -s "yq -ry .link[0] $tmp/test_link/main.fmf"
        rlAssertGrep "$default_relation: $relation_taget_02" "${rlRun_LOG}"

        rlRun "rm -rf $tmp/test_link" "0-255"
        rlRun "tmt test create test_link --template shell \
              --link $relation_taget_02 --link $relation_taget_03"
        rlAssertExists "$tmp/test_link/main.fmf"
        rlRun -s "yq -ry .link[0] $tmp/test_link/main.fmf"
        rlAssertGrep "$default_relation: $relation_taget_02" "${rlRun_LOG}"
        rlRun -s "yq -ry .link[1] $tmp/test_link/main.fmf"
        rlAssertGrep "verifies: ${relation_taget_03#verifies:}" "${rlRun_LOG}"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
