#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Positive login test for ($PROVISION_HOW)"
        rlRun -s "tmt run -a provision -h $PROVISION_HOW login -c exit" 0-255
        rlAssertGrep "login: Starting interactive shell" "$rlRun_LOG"
    rlPhaseEnd

    if [[ $PROVISION_HOW == "virtual" ]]; then
        image_url="FOOOOO"
        rlPhaseStartTest "Negative login test for $PROVISION_HOW (image url = $image_url)"
            rlRun -s "tmt run -a provision -h $PROVISION_HOW -i $image_url login -c exit" 0-255 \
                "disallowed to login into guest which is virtual if image url is invalid"
            rlAssertNotGrep "login: Starting interactive shell" "$rlRun_LOG"
            rlAssertGrep "Could not get image url" "$rlRun_LOG"
        rlPhaseEnd

        image_url="file:///rubbish"
        rlPhaseStartTest "Negative login test for $PROVISION_HOW (image url = $image_url)"
            rlRun -s "tmt run -a provision -h $PROVISION_HOW -i $image_url login -c exit" 0-255 \
                "disallowed to login into guest which is virtual if image url is invalid"
            rlAssertNotGrep "login: Starting interactive shell" "$rlRun_LOG"
            rlAssertGrep "Image .*rubbish' not found" "$rlRun_LOG"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
