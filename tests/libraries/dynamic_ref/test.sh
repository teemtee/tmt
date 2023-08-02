#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

set -o pipefail

rlJournalStart
    rlPhaseStartSetup "Prepare git repos"
        testdir=$PWD
        rlRun "repo1=\$(mktemp -d)"
        rlRun "repo2=\$(mktemp -d)"
        # Create test repo
        rlRun "cp data/test.sh $repo1"
        cat <<EOF > $repo1/main.fmf
/first:
  test: bash test.sh
  framework: beakerlib
  require:
  - name: /dynref
    type: library
    url: $repo2
    ref: "@dynamic-ref"
EOF
        rlRun "tmt init $repo1"
        rlRun "pushd $repo1"
        rlRun "git config --global init.defaultBranch main"
        rlRun "git init"
        rlRun "git config --local user.email me@localhost.localdomain"
        rlRun "git config --local user.name m e"
        rlRun "git add -A"
        rlRun "git commit -m initial"
        rlRun "popd"
        # Create library repo
        rlRun "tmt init $repo2"
        rlRun "pushd $repo2"
        rlRun "git init"
        rlRun "git config --local user.email me@localhost.localdomain"
        rlRun "git config --local user.name m e"
        rlRun "cp $testdir/data/dynamic-ref $repo2"
        rlRun "git add -A"
        rlRun "git commit -m first"
        rlRun "git checkout -b otherbranch"
        rlRun "mkdir dynref"
        rlRun "cp -r $testdir/data/lib.sh $repo2/dynref"
        cat <<EOF > $repo2/dynref/main.fmf
test: bash lib.sh
framework: beakerlib
EOF
        rlRun "git add -A"
        rlRun "git commit -m second"
        rlRun "git checkout main"
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Search for lib in a dynamically resolved branch"
        rlRun "pushd $repo1"
        rlRun -s "tmt --context foo=1 run --rm -a -vvv -ddd discover provision -h local"
        rlAssertGrep "Dynamic 'ref' definition file '.*' detected." $rlRun_LOG -E
        rlAssertGrep "Dynamic 'ref' resolved as 'otherbranch'." $rlRun_LOG
        rlAssertGrep "total: 1 test passed" $rlRun_LOG
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $repo1 $repo2" 0 "Remove temporary directories"
    rlPhaseEnd
rlJournalEnd
