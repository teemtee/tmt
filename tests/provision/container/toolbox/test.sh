#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "toolbox_container_name=\$(uuidgen)" 0 "Generate toolbox container name"
    rlPhaseEnd

    rlPhaseStartTest "Create toolbox container"
        rlRun "toolbox create -y $toolbox_container_name"
    rlPhaseEnd

    toolbox_run() {
      local command="toolbox run --container $toolbox_container_name $*"
      echo "Command: $command"
      eval "$command"
    }

    # https://packit.dev/docs/configuration/upstream/tests#environment-variables
    if env | grep -q PACKIT_COPR_PROJECT; then
        rlPhaseStartTest "Packit execution: Install tmt in from copr repository"
            TMT_COMMAND=tmt

            rlRun "type toolbox_run"

            # Install tmt from the copr repository, we need only the container provisioner
            rlRun "toolbox_run sudo dnf -y install dnf-plugins-core"
            rlRun "toolbox_run sudo dnf -y copr enable $PACKIT_COPR_PROJECT"
            rlRun "toolbox_run sudo dnf -y install tmt-provision-container"
        rlPhaseEnd
    else
        rlPhaseStartTest "Local execution: install tmt via hatch"
            TOOLBOX_TREE="/var/tmp/tree"
            TMT_COMMAND="env -C ${TOOLBOX_TREE} hatch -e dev run env -C /tmp tmt"
            rlRun "type toolbox_run"

            # install all dependencies needed for hatch installation
            rlRun "toolbox_run sudo dnf -y install gcc hatch krb5-devel libpq-devel libvirt-devel python-devel"

            # if running in toolbox, we will copy TMT_TREE from the toolbox container
            if [ -e "/run/.toolboxenv" ]; then
                COPY_FROM="$(grep name= /run/.containerenv | sed 's/name="\(.*\)"/\1/'):"
            fi

            # get tmt project root directory
            TMT_TREE=$(git rev-parse --show-toplevel)

            # copy tmt project into the toolbox container
            rlRun "podman cp ${COPY_FROM}${TMT_TREE} $toolbox_container_name:${TOOLBOX_TREE}"
        rlPhaseEnd
    fi

    rlPhaseStartTest "Print tmt version installed in toolbox"
        rlRun "toolbox_run $TMT_COMMAND --version"
    rlPhaseEnd

    rlPhaseStartTest "Add podman wrapper"
        rlRun "podman cp podman_wrapper $toolbox_container_name:/usr/bin/podman"
        rlRun "toolbox_run podman --version"
    rlPhaseEnd

    rlPhaseStartTest "Verify container provisioner works from toolbox"
        rlRun RUNID="$(mktemp -u)"
        rlRun -s "toolbox_run env -C /tmp ${TMT_COMMAND} run -i ${RUNID} -a -vvv provision -h container -i fedora execute -h tmt -s \\\"echo hello from container\\\""
        rlAssertGrep "content: hello from container" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "toolbox rm -f $toolbox_container_name" 0 "Remove toolbox container"
    rlPhaseEnd
rlJournalEnd
