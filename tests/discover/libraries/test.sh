#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "tmt='tmt run -arvvvddd plan --name'"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Certificate"
        rlRun -s "$tmt 'rpm|fmf|nick|duplicate'"
        rlAssertGrep "Fetch library 'openssl/certgen'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Apache"
        rlRun -s "$tmt apache"
        rlAssertGrep "Fetch library 'httpd/http'" $rlRun_LOG
        rlAssertGrep "Fetch library 'openssl/certgen'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Recommend"
        rlRun -s "$tmt recommend" 0
        rlAssertGrep "Fetch library 'openssl/certgen'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Conflict"
        rlRun -s "$tmt conflict" 2
        rlAssertGrep 'Library.*conflicts' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Destination"
        rlRun -s "$tmt destination" 0
        rlAssertGrep 'Cloning into.*custom/openssl' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Missing"
        rlRun -s "$tmt missing/repository" 2
        rlAssertGrep 'Authentication failed.*something' $rlRun_LOG
        rlRun -s "$tmt missing/library" 2
        rlAssertGrep 'dnf install.*openssl/wrong' $rlRun_LOG
        rlRun -s "$tmt missing/metadata" 2
        rlAssertGrep 'Repository .* does not contain fmf metadata.' $rlRun_LOG
        rlRun -s "$tmt missing/reference" 2
        rlAssertGrep 'Reference .* not found.' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Deep"
        rlRun -s "$tmt file"
        rlAssertGrep 'the library is stored deep.' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Strip git suffix"
        rlRun -s "$tmt strip_git_suffix" 0
        rlAssertGrep "summary: 3 tests selected" $rlRun_LOG
        rlAssertGrep "/strip_git_suffix/test2" $rlRun_LOG
        rlAssertGrep \
            "Detected library '{'url': 'https://github.com/teemtee/fmf.git'}'." \
            "$rlRun_LOG"
        rlAssertNotGrep 'Library.*conflicts with already fetched library' \
            "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
