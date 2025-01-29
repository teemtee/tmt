#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

#
# The test works in 3 auto-detected modes:
#
# 1. Run via `tmt` in Packit environment
#
# 2. Run locally, e.g. via `tmt try`
#
# 3. Running directly the test script `./test.sh` as a non-root user
#
# Running toolbox under root user does not work well, so in case of 1. and 2. a separate
# account `toolbox` is created. The user needs to have a working dbus session available,
# so additional steps are taken to activate systemd user session and set required environment
# variables.
#
# In case of 1. the tmt is installed from the copr repository created by Packit.
#
# In case of 2. and 3. we need to install tmt from the sources in the toolbox container.
# For 2. the sources are copied `TMT_TREE` and in case of 3. from the current git repository.
#

rlJournalStart
    rlPhaseStartSetup
        rlRun "toolbox_container_name=\$(uuidgen)" 0 "Generate toolbox container name"

        # When running via tmt, we will use a new user to run toolbox
        if env | grep -Eq "(PACKIT_COPR_PROJECT|TMT_TREE)"; then
          rlRun "toolbox_user=toolbox" 0 "Generate toolbox container name"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Create toolbox container"
        # When run via tmt, we will use a test user, toolbox under root does not work well
        if env | grep -Eq "(PACKIT_COPR_PROJECT|TMT_TREE)"; then

          # Add a toolbox user
          rlRun "useradd $toolbox_user"
          rlRun "toolbox_user_id=$(id -u $toolbox_user)"

          # Make sure systemd user session runs for the new user
          rlRun "loginctl enable-linger $toolbox_user"

          # Add required environment variables to the user
          rlRun "echo export XDG_RUNTIME_DIR=/run/user/$toolbox_user_id >> /home/$toolbox_user/.bashrc"
          rlRun "echo export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$toolbox_user_id/bus >> /home/$toolbox_user/.bashrc"

          rlRun "sudo -iu $toolbox_user toolbox create -y $toolbox_container_name"

        # When running manually ./test.sh, just create the toolbox, no additional setup needed
        else
          rlRun "toolbox create -y $toolbox_container_name"
        fi
    rlPhaseEnd

    toolbox_run() {
      if [ -n "$toolbox_user" ]; then
         local command="sudo -iu $toolbox_user toolbox run --container $toolbox_container_name $*"
      else
         local command="toolbox run --container $toolbox_container_name $*"
      fi
      echo "Command: $command"
      eval "$command"
    }

    # Execution in Packit via tmt
    # https://packit.dev/docs/configuration/upstream/tests#environment-variables
    if env | grep -q PACKIT_COPR_PROJECT; then
        rlPhaseStartTest "Packit execution: Install tmt in from copr repository"
            TMT_COMMAND=tmt

            rlRun "type toolbox_run"

            # Install tmt from the copr repository, we need only the container provisioner
            rlRun "toolbox_run sudo dnf -y install dnf-plugins-core"
            rlRun "toolbox_run sudo dnf -y copr enable $PACKIT_COPR_PROJECT"
            rlRun "toolbox_run sudo dnf -y install tmt+provision-container"
        rlPhaseEnd

    # Execution locally via tmt
    elif env | grep -q TMT_TREE; then
        rlPhaseStartTest "Local execution via tmt: Install tmt from TMT_TREE"
            TOOLBOX_TREE="/var/tmp/tree"
            TMT_COMMAND="env -C ${TOOLBOX_TREE} hatch -e dev run env -C /tmp tmt"

            rlRun "type toolbox_run"

            # Install all dependencies needed for hatch installation
            rlRun "toolbox_run sudo dnf -y install git gcc hatch krb5-devel libpq-devel libvirt-devel python-devel"

            # Create a copy of the tmt tree, to mitigate possible permission issues
            rlRun "cp -Rf ${TMT_TREE} ${TOOLBOX_TREE}"

            # Copy tmt project into the toolbox container
            rlRun "sudo -iu ${toolbox_user} podman cp ${TOOLBOX_TREE} $toolbox_container_name:${TOOLBOX_TREE}"

            # Fix permissions for the toolbox user
            rlRun "toolbox_run sudo chown -Rf ${toolbox_user}:${toolbox_user} ${TOOLBOX_TREE}"

            # Initialize git in tmt tree, it is required for development installation
            # and the tmt tree is not a git repository.
            rlRun "toolbox_run git -C ${TOOLBOX_TREE} init"
        rlPhaseEnd

    # Execution locally via ./test.sh
    else
        rlPhaseStartTest "Local execution: install tmt via hatch"
            TOOLBOX_TREE="/var/tmp/tree"
            TMT_COMMAND="env -C ${TOOLBOX_TREE} hatch -e dev run env -C /tmp tmt"
            rlRun "type toolbox_run"

            # Install all dependencies needed for hatch installation
            rlRun "toolbox_run sudo dnf -y install gcc hatch krb5-devel libpq-devel libvirt-devel python-devel"

            # If running in toolbox, we will copy TMT_TREE from the toolbox container
            if [ -e "/run/.toolboxenv" ]; then
                COPY_FROM="$(grep name= /run/.containerenv | sed 's/name="\(.*\)"/\1/'):"
            fi

            # Get tmt project root directory
            TMT_TREE=$(git rev-parse --show-toplevel)

            # Copy tmt project into the toolbox container
            rlRun "podman cp ${COPY_FROM}${TMT_TREE} $toolbox_container_name:${TOOLBOX_TREE}"
        rlPhaseEnd
    fi

    rlPhaseStartTest "Print tmt version installed in toolbox"
        rlRun "toolbox_run $TMT_COMMAND --version"
    rlPhaseEnd

    rlPhaseStartTest "Add podman wrapper"
        # Copy the wrapper from the toolbox user, the containers are local to the user.
        # Need to use a copy of the wrapper, the TMT_TREE is a volume mount and thus
        # it is not accessible to the toolbox user.
        if [ -n "${toolbox_user}" ]; then
            rlRun "cp podman_wrapper /tmp/podman_wrapper"
            rlRun "sudo -iu ${toolbox_user} podman cp /tmp/podman_wrapper $toolbox_container_name:/usr/bin/podman"
        # No dedicated user for toolbox, copy it directly
        else
            rlRun "podman cp podman_wrapper $toolbox_container_name:/usr/bin/podman"
        fi
        rlRun "toolbox_run podman --version"
    rlPhaseEnd

    rlPhaseStartTest "Verify container provisioner works from toolbox"
        rlRun RUNID="$(mktemp -u)"
        rlRun -s "toolbox_run env -C /tmp ${TMT_COMMAND} run -i ${RUNID} -a -vvv provision -h container -i registry.fedoraproject.org/fedora:latest execute -h tmt -s \\\"echo hello from container\\\""
        rlAssertGrep "content: hello from container" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "toolbox rm -f $toolbox_container_name" 0 "Remove toolbox container"
        if [ -n "$toolbox_user" ]; then
            rlRun "userdel -rf toolbox"
        fi
    rlPhaseEnd
rlJournalEnd
