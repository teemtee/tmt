#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "IMAGE_MODE=${IMAGE_MODE:-no}"
        if [ "$IMAGE_MODE" = "yes" ]; then
            rlRun "IMAGES='$TEST_IMAGE_MODE_IMAGES'"
        fi
        rlRun "pushd data"
    rlPhaseEnd

    while IFS= read -r image; do
        if [ -n "$image" ]; then
            image_opt="--image=$image"
        fi

        assert_image_mode() {
            is_image_mode "$image" || return
            rlAssertGrep "building container image from collected commands" $rlRun_LOG
            rlAssertGrep "switching to new image" $rlRun_LOG
            rlAssertGrep "rebooting to apply new image" $rlRun_LOG
        }

        rlPhaseStartTest "Custom Script"
            rlRun -s "tmt run -arv provision --how=$PROVISION_HOW $image_opt plan -n custom" 0 "Prepare using a custom script"
            assert_image_mode
        rlPhaseEnd

        rlPhaseStartTest "Commandline Script"
            rlRun "tmt run -arv provision --how=$PROVISION_HOW $image_opt plan -n custom \
                prepare -h shell -s './prepare.sh'" 0 "Prepare using a custom script from cmdline"
            assert_image_mode
        rlPhaseEnd

        rlPhaseStartTest "Multiple Commandline Scripts"
            # NOTE: These paths need to persist from the image and survive a reboot
            # See https://developers.redhat.com/articles/2025/08/25/what-image-mode-3-way-merge
            rlRun "FIRST=/var/share/first SECOND=/var/share/second"
            rlRun -s "tmt run -arv -e FIRST=$FIRST -e SECOND=$SECOND provision --how=$PROVISION_HOW $image_opt plans -n multiple \
                prepare -h shell -s 'touch $FIRST' -s 'touch $SECOND'"
            assert_image_mode
        rlPhaseEnd

        # TODO: #4785 Preparing from a remote script is broken in Image Mode
        if [ "$IMAGE_MODE" != "yes" ]; then
            rlPhaseStartTest "Remote Script"
                rlRun -s "tmt -vvv run provision --how=$PROVISION_HOW $image_opt prepare finish cleanup plan -n url" 0 "Prepare using a remote script"
                rlAssertGrep "Hello world" "$rlRun_LOG" #check for the prepare script
                rlAssertGrep "third" "$rlRun_LOG" # check for the finish script
                assert_image_mode
            rlPhaseEnd
        fi
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
