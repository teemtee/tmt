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

    rlPhaseStartTest "Recommend"
        rlRun -s "$tmt recommend" 0
        rlAssertGrep "Fetch library 'openssl/certgen'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Conflict"
        # TODO: Provide a better test covering the expected expansion defined in tmt.libraries.resolve_dependencies
        rlRun -s "tmt run -arvvvddd discover plan --name conflict" 0
        rlAssertGrep "Fetch library 'openssl/certgen'" $rlRun_LOG
        rlAssertGrep "Detected library '{'url': 'https://github.com/beakerlib/openssl', 'name': '/certgen', 'type': 'library'}'." $rlRun_LOG
        rlAssertGrep "Fetch library 'certgen/certgen'" $rlRun_LOG
        rlAssertGrep "Detected library '{'url': 'https://github.com/redhat-qe-security/certgen', 'name': '/certgen', 'type': 'library'}'." $rlRun_LOG
        rlAssertGrep "Detected library '{'url': 'https://github.com/beakerlib-libraries/certgen/', 'name': '/certgen', 'nick': 'openssl', 'type': 'library'}'." $rlRun_LOG
        rlAssertGrep "Reusing previously fetched library 'openssl/certgen' from openssl/certgen (https://github.com/beakerlib/openssl#master)" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Destination"
        rlRun -s "tmt run --id $tmp/destination --keep discover -vvvddd plan --name destination"
        rlAssertGrep "custom/example" $rlRun_LOG -s
        rlAssertExists "$tmp/destination/plan/certificate/destination/discover/default-0/custom/example/file/lib.sh"
    rlPhaseEnd

    rlPhaseStartTest "Missing"
        rlRun -s "$tmt missing/repository" 2
        rlAssertGrep 'Authentication failed.*something' $rlRun_LOG
        rlRun -s "$tmt missing/library" 2
        rlAssertGrep 'dnf.*install.*openssl/wrong' $rlRun_LOG
        rlRun -s "$tmt missing/metadata" 2
        rlAssertGrep "fail: Failed to process beakerlib libraries (/) for test '/certificate/missing/metadata'" $rlRun_LOG
        rlRun -s "$tmt missing/reference" 2
        rlAssertGrep 'Reference .* not found.' $rlRun_LOG
        rlRun -s "$tmt missing/node-metadata" 2
        rlAssertGrep "fail: Failed to process beakerlib libraries (/dir-without-fmf) for test '/certificate/missing/node-metadata'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Deep"
        rlRun -s "$tmt file"
    rlPhaseEnd

    rlPhaseStartTest "Strip git suffix"
        rlRun -s "$tmt strip-git-suffix" 0
        rlAssertGrep "summary: 3 tests selected" $rlRun_LOG
        rlAssertGrep "Detected library.*beakerlib/database.git.*mariadb" "$rlRun_LOG"
        rlAssertNotGrep "Library.*conflicts with already fetched library" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Attempt github/beakerlib lookup just once per repo"
        rlRun "tmt run --id $tmp/querying plan --name querying discover"
        # We attempted to clone
        rlAssertGrep "git clone .*beakerlib/FOOBAR" "$tmp/querying/log.txt"
        # We know it doesn't exist
        rlAssertGrep "Repository 'https://github.com/beakerlib/FOOBAR' not found." "$tmp/querying/log.txt"
        # We do two attempts for clone (with --depth=1 and three retries without it)
        LINES=$(grep "Run command: git clone .*beakerlib/FOOBAR" "$tmp/querying/log.txt" | wc -l)
        rlAssertEquals "Just four clone calls on non-existent repository" "4" "$LINES"
        # However we do it all just once
        LINES=$(grep "Repository 'https://github.com/beakerlib/FOOBAR' not found." "$tmp/querying/log.txt" | wc -l)
        rlAssertEquals "Just one attempt on non-existent repository" "1" "$LINES"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
