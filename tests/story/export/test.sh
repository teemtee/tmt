#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_internal_fields () {
    log="$1"

    rlAssertNotGrep " _" $log
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Export to yaml (minimal story)"
        rlRun -s "tmt story export mini --how=yaml"
        rlAssertGrep "name: /mini" $rlRun_LOG
        rlAssertGrep "order: 50" $rlRun_LOG
        rlAssertGrep "story: As a user I want this and that" $rlRun_LOG

        assert_internal_fields "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Export to yaml (full story)"
        rlRun -s "tmt story export full --how=yaml"
        rlAssertGrep "name: /full" $rlRun_LOG
        rlAssertGrep "summary: Story keys are correctly displayed" $rlRun_LOG
        rlAssertGrep "description: Some description" $rlRun_LOG
        rlAssertGrep "enabled: true" $rlRun_LOG
        rlAssertGrep "order: 70" $rlRun_LOG
        rlAssertGrep "id: e3a9a8ed-4585-4e86-80e8-1d99eb5345a9" $rlRun_LOG
        rlAssertGrep "tier: '3'" $rlRun_LOG
        rlAssertGrep "story: As a user I want this and that" $rlRun_LOG
        rlAssertGrep "title: A Concise Title" $rlRun_LOG
        rlAssertGrep "priority: must have" $rlRun_LOG
        assert_internal_fields "$rlRun_LOG"
        rlRun "yq .[].link[] $rlRun_LOG | grep -- 'implemented-by\": \"/some/code.py'"
        rlRun "yq .[].tag[] $rlRun_LOG | grep -- 'foo'"
        rlRun "yq .[].example[] $rlRun_LOG | grep -- 'An inspiring example'"
    rlPhaseEnd

    rlPhaseStartTest "Export to rst (minimal story)"
        rlRun -s "tmt story export mini --how=rst"
        rlAssertGrep "\.\. _/mini:" $rlRun_LOG
        rlAssertGrep "\*As a user I want this and that\*" $rlRun_LOG
        rlRun "grep -A1 ^mini$ $rlRun_LOG | grep ====" 0 "Check for header"
        rlAssertGrep "This is a draft" $rlRun_LOG
        rlAssertGrep "Status: idea" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Export to rst (full story)"
        rlRun -s "tmt story export full --how=rst"
        rlAssertGrep "\.\. _/full:" $rlRun_LOG
        rlAssertGrep "Story keys are correctly displayed" $rlRun_LOG
        rlAssertGrep "Some description" $rlRun_LOG
        rlAssertGrep "\*As a user I want this and that\*" $rlRun_LOG
        rlRun "grep -A1 '^A Concise Title$' $rlRun_LOG | grep ====" 0 "Check for header"
        rlRun "grep -A5 '^\*\*Examples:\*\*$' $rlRun_LOG | grep 'An inspiring example'"
        rlAssertNotGrep "This is a draft" $rlRun_LOG
        rlAssertGrep "Status: implemented" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Export with a custom template"
        rlRun -s "tmt story export mini --how=template --template=../story-template.j2"
        rlAssertGrep "This is a test template, it should have access to the story: \"/mini\" means \"As a user I want this and that\"." "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
