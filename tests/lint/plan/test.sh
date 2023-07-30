#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        if [ "$EXPLICIT_ROOT" = "yes" ]; then
            tmt="tmt --root data"
        else
            tmt="tmt"
            rlRun "pushd data"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Good"
        rlRun -s "$tmt plan lint good"
        rlAssertGrep "/good" $rlRun_LOG
        rlAssertNotGrep 'warn ' $rlRun_LOG
        rlRun "rm $rlRun_LOG"

        rlRun -s "$tmt plan lint valid_fmf"
        rlAssertGrep "pass P005 remote fmf id in \"default-0\" is valid" $rlRun_LOG
        rlAssertNotGrep 'warn ' $rlRun_LOG
        rlRun "rm $rlRun_LOG"

        rlRun -s "$tmt plan lint multi_execute"
        rlAssertGrep "/multi_execute" $rlRun_LOG
        rlAssertNotGrep 'fail ' $rlRun_LOG
        rlRun "rm $rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Bad"
        rlRun -s "$tmt plan lint bad" 1
        rlAssertGrep "warn C000 fmf node failed schema validation" $rlRun_LOG
        rlAssertGrep "warn C001 summary key is missing" $rlRun_LOG
        rlAssertGrep "fail P002 execute step must be defined with \"how\"" $rlRun_LOG

        rlRun -s "$tmt plan lint duplicate_names" 1
        rlAssertGrep "fail P006 duplicate phase name 'duplicate' in step 'discover'" $rlRun_LOG
        rlAssertGrep "fail P006 duplicate phase name 'duplicate' in step 'prepare'" $rlRun_LOG

        rlRun -s "$tmt plan lint invalid_how" 1
        rlAssertGrep "warn C000 value of \"how\" is not \"shell\"" $rlRun_LOG
        rlAssertGrep "warn C000 value of \"how\" is not \"fmf\"" $rlRun_LOG
        rlAssertGrep "warn C000 value of \"how\" is not \"tmt\"" $rlRun_LOG
        rlAssertGrep "warn C000 key \"name\" not recognized by schema /schemas/execute/upgrade" $rlRun_LOG
        rlAssertGrep "warn C000 value of \"how\" is not \"upgrade\"" $rlRun_LOG
        rlAssertGrep "warn C000 fmf node failed schema validation" $rlRun_LOG
        rlAssertGrep "fail P003 unknown execute method \"somehow\" in \"default-0\"" $rlRun_LOG
        rlAssertGrep "fail P004 unknown discover method \"somehow\" in \"default-0\"" $rlRun_LOG

        rlRun -s "$tmt plan lint invalid_url" 1
        rlAssertGrep "fail P005 remote fmf id in \"default-0\" is invalid, repo 'http://invalid-url' cannot be cloned" $rlRun_LOG

        rlRun -s "$tmt plan lint invalid_ref" 1
        rlAssertGrep "fail P005 remote fmf id in \"default-0\" is invalid, git ref 'invalid-ref-123456' is invalid" $rlRun_LOG

        rlRun -s "$tmt plan lint invalid_path" 1
        rlAssertGrep "fail P005 remote fmf id in \"default-0\" is invalid, path '/invalid-path-123456' is invalid" $rlRun_LOG

        rlRun -s "$tmt plan lint multi_discover" 1
        rlAssertGrep "pass P005 remote fmf id in \"a\" is valid" $rlRun_LOG
        rlAssertGrep "fail P005 remote fmf id in \"b\" is invalid, repo 'http://invalid-url' cannot be cloned" $rlRun_LOG

        rlRun -s "$tmt plan lint invalid_attr" 1
        rlAssertGrep "warn C000 fmf node failed schema validation" $rlRun_LOG
        rlAssertGrep "warn C001 summary key is missing" $rlRun_LOG
        rlAssertGrep "fail P001 unknown key \"discove\" is used" $rlRun_LOG
        rlAssertGrep "fail P001 unknown key \"environmen\" is used" $rlRun_LOG
        rlAssertGrep "fail P001 unknown key \"summaryABCDEF\" is used" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "P007: step phases require existing guests and roles"
        rlRun -s "$tmt plan lint --list-checks"
        rlAssertGrep "P007: step phases require existing guests and roles" $rlRun_LOG

        rlRun -s "$tmt plan lint /where-guest-role-mismatch" 1
        rlAssertGrep "fail P007 prepare phase 'default-0' needs guest or role 'client-1', guests 'server-1', 'server-2' and roles 'server' were found" $rlRun_LOG
        rlAssertGrep "pass P007 prepare phase 'default-1' shall run on guest 'server-1'" $rlRun_LOG
        rlAssertGrep "pass P007 prepare phase 'default-2' shall run on role 'server'" $rlRun_LOG
        rlAssertGrep "fail P007 execute phase 'default-0' needs guest or role 'client-1', guests 'server-1', 'server-2' and roles 'server' were found" $rlRun_LOG
        rlAssertGrep "pass P007 execute phase 'default-1' shall run on guest 'server-1'" $rlRun_LOG
        rlAssertGrep "pass P007 execute phase 'default-2' shall run on role 'server'" $rlRun_LOG
        rlAssertGrep "fail P007 finish phase 'default-0' needs guest or role 'client-2', guests 'server-1', 'server-2' and roles 'server' were found" $rlRun_LOG
        rlAssertGrep "pass P007 finish phase 'default-1' shall run on guest 'server-2'" $rlRun_LOG
        rlAssertGrep "pass P007 finish phase 'default-2' shall run on role 'server'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        if [ "$EXPLICIT_ROOT" != "yes" ]; then
            rlRun "popd"
        fi
    rlPhaseEnd
rlJournalEnd
