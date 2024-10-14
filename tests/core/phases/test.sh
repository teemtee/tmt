#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "rundir=$(mktemp -d)"
        rlRun "pushd data"

        run="tmt --log-topic=cli-invocations run -i $rundir --scratch -a"

        function check() {
            rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how):\\(.order)\"' $rundir/plans/$1/report/step.yaml"
            rlAssertEquals "$2" "$(cat $rlRun_LOG)" "$3"
        }
    rlPhaseEnd

    rlPhaseStartTest "Test /default-plan alone"
        rlRun -s "$run plan -n /default-plan"

        check "default-plan" "A single 'display' phase shall exist" "default-0:display:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /default-plan with a single CLI phase"
        rlRun -s "$run plan -n /default-plan \
            report -h html"

        check "default-plan" "A single 'html' phase shall exist" "default-0:html:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /default-plan with multiple CLI phases"
        rlRun -s "$run plan -n /default-plan \
            report -h html \
            report -h junit"

        check "default-plan" "A single 'junit' phase shall exist" "default-0:junit:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /default-plan with a single CLI phase inserted"
        rlRun -s "$run plan -n /default-plan \
            report --insert -h html"

        check "default-plan" "A single 'display' and a single 'html' phase shall exist" "default-0:display:50
default-1:html:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-report alone"
        rlRun -s "$run plan -n /with-report"

        check "with-report" "A single 'html' phase shall exist" "default-0:html:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-report with a single CLI phase"
        rlRun -s "$run plan -n /with-report \
            report -h display"

        check "with-report" "A single 'display' phase shall exist" "default-0:display:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-report with multiple phases"
        rlRun -s "$run plan -n /with-report \
            report -h display \
            report -h junit"

        check "with-report" "A single 'junit' phase shall exist" "default-0:junit:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports"
        rlRun -s "$run plan -n /with-multiple-reports"

        check "with-multiple-reports" "Two 'html' phases shall exist" "default-0:html:50
default-1:html:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports with a single CLI phase"
        rlRun -s "$run plan -n /with-multiple-reports \
            report -h display"

        check "with-multiple-reports" "Two 'display' phases shall exist" "default-0:display:50
default-1:display:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports with multiple CLI phases"
        rlRun -s "$run plan -n /with-multiple-reports \
            report -h display \
            report -h junit"

        check "with-multiple-reports" "Two 'junit' phases shall exist" "default-0:junit:50
default-1:junit:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports with --insert's"
        rlRun -s "$run plan -n /with-multiple-reports \
            report --insert -h junit \
            report --insert -h junit"

        check "with-multiple-reports" "Two 'html' & extra 'junit' phases shall exist" "default-0:html:50
default-1:html:50
default-2:junit:50
default-3:junit:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports with --insert's & action-less phase"
        rlRun -s "$run plan -n /with-multiple-reports \
            report --insert -h junit \
            report --insert -h junit \
            report -h display"

        check "with-multiple-reports" "Four 'display' phases shall exist" "default-0:display:50
default-1:display:50
default-2:display:50
default-3:display:50"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports with --update"
        rlRun -s "$run plan -n /with-multiple-reports \
            report --update --name default-0 -h html --display-guest never"

        check "with-multiple-reports" "Two 'html' phases shall exist" "default-0:html:50
default-1:html:50"

        rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how):\\(.\"display-guest\")\"' $rundir/plans/with-multiple-reports/report/step.yaml"
        rlAssertEquals "default-0 shall never display guests" "$(cat $rlRun_LOG)" "default-0:html:never
default-1:html:auto"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports with --update-missing"
        rlRun -s "$run plan -n /with-multiple-reports \
            report --update-missing --name default-0 -h html --display-guest auto \
            report --update-missing --name default-1 -h html --display-guest never"

        check "with-multiple-reports" "Two 'html' phases shall exist" "default-0:html:50
default-1:html:50"

        rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how):\\(.\"display-guest\")\"' $rundir/plans/with-multiple-reports/report/step.yaml"
        rlAssertEquals "default-0 shall keep its setting, default-1 shall never display guests" "$(cat $rlRun_LOG)" "default-0:html:always
default-1:html:never"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports with --update without --name"
        rlRun -s "$run plan -n /with-multiple-reports \
            report --update -h html --display-guest never"

        check "with-multiple-reports" "Two 'html' phases shall exist" "default-0:html:50
default-1:html:50"

        rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how):\\(.\"display-guest\")\"' $rundir/plans/with-multiple-reports/report/step.yaml"
        rlAssertEquals "default-0 and default-1 shall never display guests" "$(cat $rlRun_LOG)" "default-0:html:never
default-1:html:never"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-multiple-reports with --update-missing without --name"
        rlRun -s "$run plan -n /with-multiple-reports \
            report --update-missing -h html --display-guest never"

        check "with-multiple-reports" "Two 'html' phases shall exist" "default-0:html:50
default-1:html:50"

        rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how):\\(.\"display-guest\")\"' $rundir/plans/with-multiple-reports/report/step.yaml"
        rlAssertEquals "default-0 shall keep its setting, default-1 shall never display guests" "$(cat $rlRun_LOG)" "default-0:html:always
default-1:html:never"
    rlPhaseEnd

    rlPhaseStartTest "Test --update-missing preserves defined --how"
        rlRun -s "$run plan -n /with-report \
            report"

        check "with-report" "One 'html' phase shall exist" "default-0:html:50"

        rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how)\"' $rundir/plans/with-report/report/step.yaml"
        rlAssertEquals "default-0 shall be set to html how" "$(cat $rlRun_LOG)" "default-0:html"

        rlRun -s "$run plan -n /with-report \
            report --update-missing -h junit"

        check "with-report" "One 'html' phase shall exist" "default-0:html:50"

        rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how)\"' $rundir/plans/with-report/report/step.yaml"
        rlAssertEquals "default-0 shall be set to html how" "$(cat $rlRun_LOG)" "default-0:html"
    rlPhaseEnd

    rlPhaseStartTest "Test --update-missing sets undefined --how"
        rlRun -s "$run plan -n /without-how \
            report"

        check "without-how" "One 'display' phase shall exist" "default-0:display:60"

        rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how)\"' $rundir/plans/without-how/report/step.yaml"
        rlAssertEquals "default-0 shall be set to default how" "$(cat $rlRun_LOG)" "default-0:display"

        rlRun -s "$run plan -n /without-how \
            report --update-missing -h html"

        check "without-how" "One 'html' phase shall exist" "default-0:html:60"

        rlRun -s "yq -r '.data | .[] | \"\\(.name):\\(.how)\"' $rundir/plans/without-how/report/step.yaml"
        rlAssertEquals "default-0 shall be set to html how" "$(cat $rlRun_LOG)" "default-0:html"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-order"
        rlRun -s "$run plan -n /with-order"

        check "with-order" "A single 'html' phase shall exist" "default-0:html:60"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-order with a single CLI phase"
        rlRun -s "$run plan -n /with-order \
            report --update --name default-0 -h html"

        check "with-order" "A single 'html' phase with preserved order shall exist" "default-0:html:60"
    rlPhaseEnd

    rlPhaseStartTest "Test /with-order with --update"
        rlRun -s "$run plan -n /with-order \
            report --update --name default-0 --order 40"

        check "with-order" "A single 'html' phase with modified order shall exist" "default-0:html:40"
    rlPhaseEnd

    rlPhaseStartTest "Test whether --update can change 'how'"
        rlRun -s "$run plan -n /with-report \
            report --update --name default-0 --how junit"

        check "with-report" "A single 'junit' phase shall exist" "default-0:junit:50"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $rundir"
    rlPhaseEnd
rlJournalEnd
