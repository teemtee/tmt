#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        if ! rlIsFedora; then
          # TODO: Handle centos artifacts also
          rlDie "Skipping because non-fedora test is not implemented"
        fi
        rlRun "fedora_release=$(rlGetDistroRelease)"
        build_container_image "fedora/${fedora_release}:latest"
    rlPhaseEnd

    rlPhaseStartTest "Test artifact installation on Fedora"
        # Using make as a test package that should always be safe to install
        rlRun -s "koji list-tagged --latest f${fedora_release} make" 0 "Get the latest make build"
        # The NVR should be the first word in the last line:
        # make-4.4.1-10.fc42                        f42                   releng
        if [[ ! "$(tail -1 $rlRun_LOG)" =~ ^([^[:space:]]+) ]]; then
            rlDie "Package NVR regex failed"
        fi
        rlRun "make_nvr=${BASH_REMATCH[1]}" 0 "Get the package NVR"
        rlRun -s "koji buildinfo $make_nvr" 0 "Get the build info"
        # The build ID should be in square brackets of the first line:
        # BUILD: make-4.4.1-10.fc42 [2625600]
        if [[ ! "$(head -1 $rlRun_LOG)" =~ ^BUILD:[[:space:]]*[^[:space:]]+[[:space:]]*\[([[:digit:]]+)\] ]]; then
            rlDie "BuilID regex failed"
        fi
        rlRun "make_buildid=${BASH_REMATCH[1]}" 0 "Get the package NVR"
        # TODO: Handle VM, local and other provision also
        rlRun "tmt run -i $run --scratch -av provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest prepare --insert --how artifact --provide koji.build:$make_buildid"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
