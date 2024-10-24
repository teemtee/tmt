#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    # would be set by TMT_TEST_DATA
    tmt_test_data="default/plan/execute/data/guest/default-0/default-1/data"
    tmt_results_yaml_file="$tmp/default/plan/execute/results.yaml"

    rlPhaseStartTest
        rlRun "tmt run -vfi $tmp -a provision -h container"
        FILE_PATH=$tmp/$tmt_test_data/this_file.txt

        # The `TESTID` is set to same value as `TMT_TEST_SERIAL_NUMBER`. Get
        # the serial number of a first test.
        tmt_test_serial_number=$(yq -e '.[] | select(.name == "/") | .["serial-number"]' "$tmt_results_yaml_file")

        # The bundle name is suffixed with `TESTID` value
        BUNDLE_PATH="$tmp/$tmt_test_data/tmp-bundle_name-${tmt_test_serial_number}.tar.gz"

        # File was submitted and has correct content
        rlAssertExists "$FILE_PATH"
        rlAssertGrep "YES" "$FILE_PATH"

        # Bundle was submitted and has correct content
        rlAssertExists "$BUNDLE_PATH"
        rlRun "tar tzf $BUNDLE_PATH | grep /this_file.txt" \
            0 "Bundle contains an expected file"

        # FIXME - Present this information somehow to the user
        # (that they have some files...)
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
