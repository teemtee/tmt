#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "cp -a data $tmp"
        rlRun 'pushd $tmp/data/parent/child'
        rlRun 'set -o pipefail'
    rlPhaseEnd

    rlPhaseStartTest 'Import metadata'
        rlRun -s 'tmt test import --no-nitrate'
        rlAssertGrep 'Makefile found in' $rlRun_LOG
        rlAssertGrep 'summary: Simple smoke test' 'main.fmf'
        rlRun 'yq .require[] main.fmf | grep tmt'
        rlRun 'yq .recommend[] main.fmf | grep fmf'
    rlPhaseEnd

    rlPhaseStartTest 'Check duplicates'
        rlAssertNotGrep 'component:' 'main.fmf'
        rlAssertNotGrep 'test:' 'main.fmf'
        rlAssertNotGrep 'duration:' 'main.fmf'
    rlPhaseEnd

    rlPhaseStartTest 'Check rhts-environment removal'
        rlAssertGrep 'Removing.*rhts-environment' $rlRun_LOG
        rlAssertNotGrep 'rhts-environment' 'runtest.sh'
    rlPhaseEnd

    rlPhaseStartTest 'Check beakerlib path update'
        rlAssertGrep 'Replacing old beakerlib path' $rlRun_LOG
        rlAssertGrep '/usr/share/beakerlib/beakerlib.sh' 'runtest.sh'
        rlAssertNotGrep '/usr/lib/beakerlib/beakerlib.sh' 'runtest.sh'
        rlAssertNotGrep '/usr/share/rhts-library/rhtslib.sh' 'runtest.sh'
    rlPhaseEnd

    rlPhaseStartTest 'Import Restraint metadata'
        rlRun -s 'tmt test import --restraint --no-nitrate'
        rlAssertGrep 'Restraint file found in' $rlRun_LOG
        rlAssertGrep 'summary: Simple smoke test using restraint' 'main.fmf'
        rlRun 'yq .require[] main.fmf | grep "fmf\|tmt"'
        rlRun 'yq .recommend[] main.fmf | grep fmf'
        rlAssertGrep 'test: bash -x ./runtest.sh' $rlRun_LOG
        rlAssertGrep 'duration: 6m' 'main.fmf'
    rlPhaseEnd

    rlPhaseStartTest 'Import both Makefile and Restraint metadata. Expect Restraint to be used.'
        rlRun -s 'tmt test import --makefile --restraint --no-nitrate'
        rlAssertGrep 'Restraint file found in' $rlRun_LOG
        rlAssertGrep 'summary: Simple smoke test using restraint' 'main.fmf'
        rlRun 'yq .require[] main.fmf | grep "fmf\|tmt"'
        rlRun 'yq .recommend[] main.fmf | grep fmf'
        rlAssertGrep 'test: bash -x ./runtest.sh' $rlRun_LOG
        rlAssertGrep 'duration: 6m' 'main.fmf'
    rlPhaseEnd

    rlPhaseStartTest 'Import specifying not to use Makefile. Verify an error is returned.'
        rlRun -s 'tmt test import --no-makefile --no-nitrate 2>&1' 2
        rlAssertGrep 'Please specify either a Makefile or a Restraint file' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Import specifying not to use Makefile or Restraint. Verify an error is returned.'
        rlRun -s 'tmt test import --no-makefile --no-restraint --no-nitrate 2>&1' 2
        rlAssertGrep 'Please specify either a Makefile or a Restraint file or a Polarion case ID' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Import metadata'
        rlRun -s 'tmt test import --no-nitrate'
        rlAssertGrep 'Makefile found in' $rlRun_LOG
        rlAssertGrep 'summary: Simple smoke test' 'main.fmf'
        rlAssertGrep 'duration: 5m' $rlRun_LOG
        rlRun 'yq .require[] main.fmf | grep tmt'
        rlRun 'yq .recommend[] main.fmf | grep fmf'
    rlPhaseEnd

    rlPhaseStartTest 'Verify error returned when no Makefile exists.'
        rlFileBackup "$tmp/data/parent/child/Makefile"
        rlRun "rm -f $tmp/data/parent/child/Makefile" 0 "Removing Makefile"
        rlRun -s 'tmt test import --no-nitrate 2>&1' 2
        rlAssertGrep 'Unable to find Makefile' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Verify error returned when no Restraint metadata file exists.'
        rlFileBackup "$tmp/data/parent/child/metadata"
        rlRun "rm -f $tmp/data/parent/child/metadata" 0 "Removing Restraint file."
        rlRun -s 'tmt test import --restraint --no-nitrate 2>&1' 2
        rlAssertGrep 'Unable to find any metadata file.' $rlRun_LOG
        rlFileRestore
    rlPhaseEnd

    rlPhaseStartTest 'Verify inheritance'
        rlRun -s 'tmt test show'
        rlAssertGrep 'component tmt' $rlRun_LOG
        rlAssertGrep 'test ./runtest.sh' $rlRun_LOG
        rlAssertGrep 'duration 5m' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Check Makefile environment variables'
        rlRun -s 'tmt test show'
        rlAssertGrep 'AVC_ERROR: +no_avc_check' $rlRun_LOG
        rlAssertGrep 'TEST: one two three' $rlRun_LOG
        rlAssertGrep 'CONTEXT: distro=fedora' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Relevant bugs'
        rlRun -s 'tmt test show'
        rlAssertGrep 'relates.*1234567' $rlRun_LOG
        rlAssertGrep 'relates.*2222222' $rlRun_LOG
        rlAssertGrep 'relates.*9876543' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Multihost'
        rlRun -s "tmt tests ls . --filter 'tag:multihost'"
        rlAssertGrep "/parent/child" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest 'Type'
        import="tmt test import --no-nitrate"
        rlRun -s "$import --type all"
        rlAssertGrep "tag: Multihost Sanity KernelTier1" $rlRun_LOG
        rlRun -s 'tmt test show'
        rlAssertGrep "tag 'Multihost', 'Sanity' and 'KernelTier1'" $rlRun_LOG
        rlRun -s "$import --type KernelTier1"
        rlAssertGrep 'tag: KernelTier1$' $rlRun_LOG
        rlRun -s 'tmt test show'
        rlAssertGrep "tag KernelTier1$" $rlRun_LOG
        rlRun -s "$import --type KernelTier1 --type SaNiTy"
        rlAssertGrep "tag: KernelTier1 SaNiTy" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Negative requires"
        rlRun 'pushd $tmp/data/parent/negative-requires'
        rlRun -s 'tmt test import --no-nitrate' '2'
        rlAssertGrep 'Excluding packages is not supported' $rlRun_LOG
        rlAssertNotExists "main.fmf"
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Empty requires"
        rlRun 'pushd $tmp/data/parent/empty-requires'
        rlRun -s 'tmt test import --makefile --no-nitrate --no-purpose' '0'
        rlAssertExists "main.fmf"
        rlRun 'cat main.fmf'
        rlAssertGrep 'recommend:\s*\[\]' "main.fmf"
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Target run having a single line"
        rlRun 'pushd $tmp/data/parent/single-line-run'
        rlRun -s 'tmt test import --makefile --no-nitrate --no-purpose' '0'
        rlAssertExists "main.fmf"
        rlRun 'cat main.fmf'
        rlRun 'yq .test main.fmf | grep "bash -x runtest.sh"'
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Target run having multiple lines"
        rlRun 'pushd $tmp/data/parent/multiple-lines-run'
        rlRun -s 'tmt test import --makefile --no-nitrate --no-purpose' '0'
        rlAssertExists "main.fmf"
        rlRun 'cat main.fmf'
        rlRun -s "yq .test main.fmf"
        rlAssertGrep "( export PS4='debug> ' && set -x;" $rlRun_LOG
        rlAssertGrep "chmod +x runtest.sh;" $rlRun_LOG
        rlAssertGrep "./runtest.sh;" $rlRun_LOG
        rlAssertGrep "chmod -x runtest.sh )" $rlRun_LOG
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
