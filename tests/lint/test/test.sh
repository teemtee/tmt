#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp -a data $tmp"
        rlRun "cp -a data_sources $tmp"
        rlRun "cp -a data_duplicate_ids $tmp"
        rlRun "pushd $tmp/data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Perfect"
        rlRun -s "tmt test lint perfect"
        rlAssertGrep 'pass' $rlRun_LOG
        rlAssertGrep 'pass T001 correct keys are used' $rlRun_LOG
        rlAssertNotGrep 'warn' $rlRun_LOG
        rlAssertNotGrep 'fail' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Good"
        rlRun -s "tmt test lint good"
        rlAssertGrep 'pass' $rlRun_LOG
        rlAssertGrep 'warn' $rlRun_LOG
        rlAssertNotGrep 'fail' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Old yaml"
        if rlRun -s "tmt test lint old-yaml" 0,2; then
            # Before fmf-1.0 we give just a warning
            rlAssertGrep "warn: /old-yaml:enabled - 'yes' is not of type 'boolean'" $rlRun_LOG
            rlAssertGrep "warn C000 fmf node failed schema validation" $rlRun_LOG
        else
            # Since fmf-1.0 old format is no more supported
            rlAssertGrep 'Invalid.*enabled.*in test' $rlRun_LOG
        fi
    rlPhaseEnd

    rlPhaseStartTest "Bad"
        rlRun -s "tmt test lint empty" 2
        rlAssertGrep "must be defined" $rlRun_LOG
        rlRun -s "tmt test lint bad-path" 1
        rlAssertGrep "fail T004 test path '.*/data/not-a-path' does not exist" $rlRun_LOG
        rlRun -s "tmt test lint bad-not-absolute" 1
        rlAssertGrep 'fail T003 directory path is not absolute' $rlRun_LOG
        rlAssertGrep "fail T004 test path '.*/data/not-absolute' does not exist" $rlRun_LOG
        rlRun -s "tmt test lint relevancy" 1
        rlAssertGrep 'fail T005 relevancy has been obsoleted by adjust' $rlRun_LOG
        # There should be no change without --fix
        for format in list text; do
            rlAssertGrep 'relevancy' "relevancy-$format.fmf"
            rlAssertNotGrep 'adjust:' "relevancy-$format.fmf"
        done
        rlRun -s "tmt test lint bad-attribute" 1
        rlAssertGrep "fail T001 unknown key \"requires\" is used" $rlRun_LOG
        rlAssertGrep "fail T001 unknown key \"serial_number\" is used" $rlRun_LOG
        rlRun -s "tmt test lint coverage" 1
        rlAssertGrep "fail T006 the 'coverage' field has been obsoleted by 'link'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Fix"
        # With --fix relevancy should be converted
        rlRun -s "tmt test lint --fix relevancy"
        rlAssertGrep 'fix  T005 relevancy converted into adjust' $rlRun_LOG
        for format in list text; do
            rlAssertNotGrep 'relevancy' "relevancy-$format.fmf"
            rlIsFedora && rlAssertGrep '#comment' "relevancy-$format.fmf"
            rlAssertGrep 'adjust:' "relevancy-$format.fmf"
            rlAssertGrep 'when: distro == rhel' "relevancy-$format.fmf"
        done
    rlPhaseEnd

    rlPhaseStartTest "Manual test"
        # Correct syntax
        rlRun -s "tmt test lint /manual_true/correct_path/pass"
        rlAssertGrep 'pass T008 correct manual test syntax' $rlRun_LOG

        # Wrong test path
        rlRun -s "tmt test lint /manual/manual_true/wrong_path" 1
        rlAssertGrep "fail T007 manual test path \".*/manual_test_passed/wrong_path.md\" does not exist" $rlRun_LOG
        rlAssertGrep "fail T008 cannot open the manual test path: Unable to open '.*/manual_test_passed/wrong_path.md'." $rlRun_LOG

        # If manual=false - don't check test attribute
        rlRun -s "tmt test lint /manual/manual_false"
        rlAssertGrep 'skip T008 not a manual test' $rlRun_LOG

        # Unknown headings
        rlRun -s "tmt test lint /manual_true/correct_path/fail1" 0
        fail="warn T008"
        rlAssertGrep "$fail unknown html heading \"<h2>Test</h2>\" is used" $rlRun_LOG
        rlAssertGrep "$fail unknown html heading "<h2>Unknown heading end</h2>" is used" $rlRun_LOG
        rlAssertGrep "$fail unknown html heading "<h3>Unknown heading begin</h3>" is used" $rlRun_LOG

        # Warn if 2 or more # Setup or # Cleanup are used
        rlAssertGrep "$fail 2 headings \"<h1>Setup</h1>\" are used" $rlRun_LOG
        rlAssertGrep "$fail 3 headings \"<h1>Cleanup</h1>\" are used" $rlRun_LOG

        # Step is used outside of test sections.
        rlAssertGrep "$fail Heading \"<h2>Step</h2>\" from the section \"Step\" is used outside of Test sections." $rlRun_LOG

        # Unexpected headings
        rlAssertGrep "$fail Headings \".*\" aren't expected in the section \"<h1>Test</h1>\"" $rlRun_LOG

        # Step isn't in pair with Expect
        rlAssertGrep "$fail The number of headings from the section \"Step\" - 2 doesn't equal to the number of headings from the section \"Expect\" - 1 in the test section \"<h1>Test two</h1>\"" $rlRun_LOG

        # Required section doesn't exist
        rlRun -s "tmt test lint /manual_true/correct_path/fail2" 0
        rlAssertGrep "warn T008 \"Test\" section doesn't exist in the Markdown file" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Lint by modified source files"
        rlRun "pushd $tmp/data_sources"

        lint_cmd="tmt test lint --source"

        # main.fmf is used by all but '/foo/special'
        rlRun -s "$lint_cmd main.fmf"
        for t in /virtual /baz/bb /foo/inner /foobar; do
            rlAssertGrep "$t" "$rlRun_LOG"
        done
        rlAssertNotGrep '/foo/special' "$rlRun_LOG"

        # foo/main.fmf is used single test
        rlRun -s "$lint_cmd $(realpath foo/main.fmf)"
        rlAssertGrep "/foo/inner" "$rlRun_LOG"
        for t in /virtual /baz/bb /foo/special /foobar; do
            rlAssertNotGrep "$t" "$rlRun_LOG"
        done

        # '.' as local directory with single file and a explicit one
        rlRun "pushd foobar"
        rlRun -s "$lint_cmd *.fmf $(realpath ../baz/bb.fmf)"
        rlAssertGrep "/foobar" "$rlRun_LOG"
        rlAssertGrep "/baz/bb" "$rlRun_LOG"
        for t in /virtual /foo/special /foo/special; do
            rlAssertNotGrep "$t" "$rlRun_LOG"
        done
        # From data_sources/foobar
        rlRun "popd"
        # From data_sources
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Lint of duplicate ids"
        rlRun "pushd $tmp/data_duplicate_ids"

        lint_cmd="tmt test lint"

        rlRun -s "$lint_cmd /no_duplicates"
        rlAssertGrep "pass G001 no duplicate ids detected" "$rlRun_LOG"

        rlRun -s "$lint_cmd /duplicates" 1
        rlAssertGrep "fail G001 duplicate id \"c258fc68-3706-44ce-9974-c0abaad5b251\" in \"/duplicates/duplicate_one\"" "$rlRun_LOG"
        rlAssertGrep "fail G001 duplicate id \"c258fc68-3706-44ce-9974-c0abaad5b251\" in \"/duplicates/duplicate_two\"" "$rlRun_LOG"

        # From data_duplicate_ids
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd" # From data
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
