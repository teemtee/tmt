#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'pushd data'
    rlPhaseEnd

    rlPhaseStartTest 'Check environment variable precedence'
        rlRun -s "tmt -vvv --feeling-safe run -a --environment VAR7=cli.run.environment --environment-file run-environment.env"

        rlAssertNotGrep "prepare.0: VAR1=test.environment"              $rlRun_LOG
        rlAssertGrep    "prepare.0: VAR2=plan.environment-file"         $rlRun_LOG
        rlAssertGrep    "prepare.0: VAR3=plan.environment"              $rlRun_LOG
        rlAssertGrep    "prepare.0: VAR4=provision.environment"         $rlRun_LOG
        rlAssertGrep    "prepare.0: VAR5=provision.environment"         $rlRun_LOG
        rlAssertGrep    "prepare.0: VAR6=cli.run.environment-file"      $rlRun_LOG
        rlAssertGrep    "prepare.0: VAR7=cli.run.environment"           $rlRun_LOG

        rlAssertNotGrep "prepare.2: VAR1=test.environment"              $rlRun_LOG
        rlAssertGrep    "prepare.2: VAR2=plan.environment-file"         $rlRun_LOG
        rlAssertGrep    "prepare.2: VAR3=plan.environment"              $rlRun_LOG
        rlAssertGrep    "prepare.2: VAR4=provision.environment"         $rlRun_LOG
        rlAssertGrep    "prepare.2: VAR5=plan.plan-environment-file"    $rlRun_LOG
        rlAssertGrep    "prepare.2: VAR6=cli.run.environment-file"      $rlRun_LOG
        rlAssertGrep    "prepare.2: VAR7=cli.run.environment"           $rlRun_LOG

        rlAssertGrep    "execute.0: VAR1=test.environment"              $rlRun_LOG
        rlAssertGrep    "execute.0: VAR2=plan.environment-file"         $rlRun_LOG
        rlAssertGrep    "execute.0: VAR3=plan.environment"              $rlRun_LOG
        rlAssertGrep    "execute.0: VAR4=provision.environment"         $rlRun_LOG
        rlAssertGrep    "execute.0: VAR5=plan.plan-environment-file"    $rlRun_LOG
        rlAssertGrep    "execute.0: VAR6=cli.run.environment-file"      $rlRun_LOG
        rlAssertGrep    "execute.0: VAR7=cli.run.environment"           $rlRun_LOG

        rlAssertNotGrep "finish.0: VAR1=test.environment"               $rlRun_LOG
        rlAssertGrep    "finish.0: VAR2=plan.environment-file"          $rlRun_LOG
        rlAssertGrep    "finish.0: VAR3=plan.environment"               $rlRun_LOG
        rlAssertGrep    "finish.0: VAR4=provision.environment"          $rlRun_LOG
        rlAssertGrep    "finish.0: VAR5=plan.plan-environment-file"     $rlRun_LOG
        rlAssertGrep    "finish.0: VAR6=cli.run.environment-file"       $rlRun_LOG
        rlAssertGrep    "finish.0: VAR7=cli.run.environment"            $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
