#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "PROVISION_OPTS='--how=$PROVISION_HOW'"
        rlRun "IS_IMAGE_MODE=no"
        if [ "$PROVISION_HOW" = "virtual-image-mode" ]; then
            . ../../images.sh || exit 1
            rlRun "IS_IMAGE_MODE=yes"
            rlRun "PROVISION_HOW=virtual"
            rlRun "IMAGE_MODE_IMAGE=$(echo "$TEST_IMAGE_MODE_IMAGES" | head -1)"
            rlRun "PROVISION_OPTS='--how=virtual --image=$IMAGE_MODE_IMAGE'"
        fi
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Custom Script"
        rlRun -s "tmt run -arv provision $PROVISION_OPTS plan -n custom" 0 "Prepare using a custom script"

        if [ "$IS_IMAGE_MODE" = "yes" ]; then
            # Verify image mode specific behavior (debug-level messages
            # like "Collected command for Containerfile" are not visible
            # at -arv verbosity)
            rlAssertGrep "building container image from collected commands" $rlRun_LOG
            rlAssertGrep "switching to new image" $rlRun_LOG
            rlAssertGrep "rebooting to apply new image" $rlRun_LOG
        fi
    rlPhaseEnd

    rlPhaseStartTest "Commandline Script"
        rlRun "tmt run -arv provision $PROVISION_OPTS plan -n custom \
            prepare -h shell -s './prepare.sh'" 0 "Prepare using a custom script from cmdline"
    rlPhaseEnd

    # TODO: On image mode, /tmp is a tmpfs cleared on reboot. The inner
    # test plan verifies files in /tmp which don't persist. Similarly,
    # the remote script URL plan's $TMT_PREPARE_SHELL_URL_REPOSITORY
    # env var is empty during the Containerfile RUN. Both need image
    # mode support in tmt core before these tests can pass.
    if [ "$IS_IMAGE_MODE" != "yes" ]; then
        rlPhaseStartTest "Multiple Commandline Scripts"
            rlRun "tmt run -arv provision $PROVISION_OPTS plans -n multiple \
                prepare -h shell -s 'touch /tmp/first' -s 'touch /tmp/second'"
        rlPhaseEnd

        rlPhaseStartTest "Remote Script"
            rlRun -s "tmt -vvv run provision $PROVISION_OPTS prepare finish cleanup plan -n url" 0 "Prepare using a remote script"
            rlAssertGrep "Hello world" "$rlRun_LOG" #check for the prepare script
            rlAssertGrep "third" "$rlRun_LOG" # check for the finish script
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
