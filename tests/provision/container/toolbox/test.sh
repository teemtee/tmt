#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

# Use `tmt try` to run this test locally, running directly the script will not work.

rlJournalStart
    rlPhaseStartSetup
        rlRun "toolbox_container_name=\$(uuidgen)" 0 "Generate toolbox container name"
        rlRun "toolbox_user=toolbox" 0 "Set user for running toolbox"
    rlPhaseEnd

    rlPhaseStartTest "Create toolbox container"
        # Add a toolbox user. Running toolbox under root user does not work well,
        # so a separate user account is created.
        rlRun "useradd $toolbox_user"
        rlRun "toolbox_user_id=$(id -u $toolbox_user)"

        # Make sure systemd user session runs for the new user. The user session
        # hosts a dbus session, which is required for toolbox.
        rlRun "loginctl enable-linger $toolbox_user"

        # Add required environment variables for toolbox to the user's environment.
        rlRun "echo export XDG_RUNTIME_DIR=/run/user/$toolbox_user_id >> /home/$toolbox_user/.bashrc"
        rlRun "echo export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$toolbox_user_id/bus >> /home/$toolbox_user/.bashrc"

        rlRun "sudo -iu $toolbox_user toolbox create -y $toolbox_container_name"
    rlPhaseEnd

    toolbox_run() {
        local command="sudo -iu $toolbox_user toolbox run --container $toolbox_container_name $*"
        echo "Command: $command"
        eval "$command"
    }

    rlPhaseStartTest "Local execution via tmt: Install tmt from TMT_TREE"
        TOOLBOX_TREE="/var/tmp/tree"
        TMT_COMMAND="env -C ${TOOLBOX_TREE} hatch -e dev run env -C /tmp tmt"

        rlRun "type toolbox_run"

        # Install make and hatch
        rlRun "toolbox_run sudo dnf -y install make hatch"

        # Create a copy of the tmt tree, to mitigate possible permission issues
        rlRun "cp -Rf ${TMT_TREE} ${TOOLBOX_TREE}"

        # Copy tmt project into the toolbox container
        rlRun "sudo -iu ${toolbox_user} podman cp ${TOOLBOX_TREE} $toolbox_container_name:${TOOLBOX_TREE}"

        # Fix permissions for the toolbox user
        rlRun "toolbox_run sudo chown -Rf ${toolbox_user}:${toolbox_user} ${TOOLBOX_TREE}"

        # Initialize git in tmt tree, it is required for development installation
        # and the tmt tree is not a git repository.
        rlRun "toolbox_run git -C ${TOOLBOX_TREE} init"

        # Install additional development dependencies
        rlRun "toolbox_run make -C ${TOOLBOX_TREE} develop"
    rlPhaseEnd

    rlPhaseStartTest "Print tmt version installed in toolbox"
        rlRun "toolbox_run $TMT_COMMAND --version"
    rlPhaseEnd

    rlPhaseStartTest "Add podman wrapper"
        # Copy the wrapper from the toolbox user, the containers are local to the user.
        # Need to use a copy of the wrapper, the TMT_TREE is a volume mount and thus
        # it is not accessible to the toolbox user.
        rlRun "cp podman_wrapper /tmp/podman_wrapper"
        rlRun "sudo -iu ${toolbox_user} podman cp /tmp/podman_wrapper $toolbox_container_name:/usr/bin/podman"
        rlRun "toolbox_run podman --version"
    rlPhaseEnd

    rlPhaseStartTest "Verify container provisioner works from toolbox"
        rlRun RUNID="$(mktemp -u)"
        rlRun -s "toolbox_run env -C /tmp ${TMT_COMMAND} run -i ${RUNID} -a -vvv provision -h container -i registry.fedoraproject.org/fedora:latest execute -h tmt -s \\\"echo hello from container\\\""
        rlAssertGrep "content: hello from container" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "toolbox rm -f $toolbox_container_name" 0 "Remove toolbox container"
        rlRun "userdel -rf toolbox"
    rlPhaseEnd
rlJournalEnd
