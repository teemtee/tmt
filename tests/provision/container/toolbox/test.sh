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
      toolbox run --container "$toolbox_container_name" "$@"
    }

    if env | grep -q PACKIT_COPR_PROJECT; then
	rlPhaseStartTest "Install tmt in from copr repository"
	    TMT_COMMAND="tmt"
	    rlRun "toolbox_run dnf -y install dnf-plugins-core"
	    rlRun "toolbox_run dnf -y copr enable $PACKIT_COPR_PROJECT"
	    rlRun "toolbox_run dnf -y install tmt-provision-container"
	rlPhaseEnd
    else
	rlPhaseStartTest "Install hatch, expecting local execution"
	    TMT_COMMAND="hatch run dev:tmt"
	    rlRun "toolbox_run dnf -y install hatch"
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
	rlRun -s "toolbox_run tmt run -a -vvv provision -h container execute -h tmt -s 'echo hello from container'"
	rlAssertGrep "content: hello from container" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "toolbox rm -f $toolbox_container_name" 0 "Remove toolbox container"
    rlPhaseEnd
rlJournalEnd
