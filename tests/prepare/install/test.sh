#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

# TODO: should these variables exist outside of this test, for all tests
# to share?
CONTAINER_IMAGES="${CONTAINER_IMAGES:-localhost/tmt/fedora/rawhide:latest
registry.fedoraproject.org/fedora:39
quay.io/centos/centos:stream8
quay.io/centos/centos:7
docker.io/library/ubuntu:22.04
ubi8
localhost/tmt/alpine:latest
localhost/tmt/fedora/coreos:stable
localhost/tmt/fedora/coreos/ostree:stable}"

# TODO: enable Ubuntu
VIRTUAL_IMAGES="${VIRTUAL_IMAGES:-fedora-rawhide
fedora-39
centos-stream-8
centos-7
fedora-coreos}"

# A couple of "is image this?" helpers, to simplify conditions.
function is_fedora_rawhide () {
    [[ "$1" =~ ^.*fedora/rawhide:.* ]] && return 0
    [[ "$1" = "fedora-rawhide" ]] && return 0

    return 1
}

function is_fedora_39 () {
    [[ "$1" =~ ^.*fedora:39 ]] && return 0
    [[ "$1" = "fedora-39" ]] && return 0

    return 1
}

function is_centos_stream_8 () {
    [[ "$1" =~ ^.*centos:stream8 ]] && return 0
    [[ "$1" = "centos-stream-8" ]] && return 0

    return 1
}

function is_centos_7 () {
    [[ "$1" =~ ^.*centos:7 ]] && return 0
    [[ "$1" = "centos-7" ]] && return 0

    return 1
}

function is_ubuntu () {
    [[ "$1" =~ ^.*ubuntu:22.04 ]] && return 0
    [[ "$1" = "ubuntu" ]] && return 0

    return 1
}

function is_ostree () {
    [[ "$1" =~ ^.*fedora/coreos/ostree:stable ]] && return 0
    [[ "$1" = "fedora-coreos" && "$PROVISION_HOW" = "virtual" ]] && return 0

    return 1
}

function is_fedora_coreos () {
    [[ "$1" =~ ^.*fedora/coreos(/ostree)?:stable ]] && return 0
    [[ "$1" = "fedora-coreos" ]] && return 0

    return 1
}

function is_fedora () {
    [[ "$1" =~ ^.*fedora.* ]] && return 0 || return 1
}

function is_centos () {
    [[ "$1" =~ ^.*centos.* ]] && return 0 || return 1
}

function is_rhel () {
    is_ubi "$1" && return 0 || return 1
}

function is_alpine () {
    [[ "$1" =~ ^.*alpine.* ]] && return 0 || return 1
}

function is_ubi () {
    [[ "$1" =~ ^.*ubi.* ]] && return 0 || return 1
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        if [ "$PROVISION_HOW" = "container" ]; then
            rlRun "IMAGES='$CONTAINER_IMAGES'"

            rlRun "make -C ../../../ images-tests"

        elif [ "$PROVISION_HOW" = "virtual" ]; then
            rlRun "IMAGES='$VIRTUAL_IMAGES'"

        else
            rlRun "IMAGES="
        fi

        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"

        rlRun "export TMT_BOOT_TIMEOUT=300"
        rlRun "export TMT_CONNECT_TIMEOUT=300"
    rlPhaseEnd

    while IFS= read -r image; do
        phase_prefix="[$PROVISION_HOW / $image]"

        rlPhaseStartTest "$phase_prefix Prepare runtime"
            [ "$PROVISION_HOW" = "container" ] && rlRun "podman images $image"

            if is_fedora_rawhide "$image"; then
                rlRun "distro=fedora-rawhide"

                if [ "$PROVISION_HOW" = "virtual" ]; then
                    rlRun "package_manager=dnf"
                else
                    rlRun "package_manager=dnf5"
                fi

            elif is_fedora_39 "$image"; then
                rlRun "distro=fedora-39"
                rlRun "package_manager=dnf"

            elif is_centos_stream_8 "$image"; then
                rlRun "distro=centos-stream-8"
                rlRun "package_manager=dnf"

            elif is_centos_7 "$image"; then
                rlRun "distro=centos-7"
                rlRun "package_manager=yum"

            elif is_ubuntu "$image"; then
                rlRun "distro=ubuntu"
                rlRun "package_manager=apt"

            elif is_fedora_coreos "$image"; then
                rlRun "distro=fedora-coreos"

                if is_ostree "$image"; then
                    rlRun "package_manager=rpm-ostree"

                elif [ "$PROVISION_HOW" = "virtual" ]; then
                    rlRun "package_manager=dnf"

                else
                    rlRun "package_manager=dnf5"

                fi

            elif is_ubi "$image"; then
                rlRun "distro=rhel-8"
                rlRun "package_manager=dnf"

            elif is_alpine "$image"; then
                rlRun "distro=alpine"
                rlRun "package_manager=apk"

            else
                rlFail "Cannot infer distro for image $image"
            fi

            tmt="tmt -vvv -c distro=$distro run --id $run --scratch finish discover provision --how $PROVISION_HOW --image $image prepare"
        rlPhaseEnd

        # TODO: find out whether all those exceptions can be simplified and parametrized...

        # TODO: cannot *successfully* install on ubi without subscribing first?
        if ! is_ubi "$image"; then
            rlPhaseStartTest "$phase_prefix Install existing packages (plan)"
                rlRun -s "$tmt plan --name /existing"

                rlAssertGrep "package manager: $package_manager" $rlRun_LOG

                if is_ubuntu "$image"; then
                    # Runs 1 extra phase, to populate local caches.
                    rlAssertGrep "summary: 3 preparations applied" $rlRun_LOG
                else
                    rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
                fi
            rlPhaseEnd

            rlPhaseStartTest "$phase_prefix Install existing packages (CLI)"
                rlRun -s "$tmt --insert --how install --package tree --package diffutils plan --name /empty"

                rlAssertGrep "package manager: $package_manager" $rlRun_LOG

                if is_ubuntu "$image"; then
                    # Runs 1 extra phase, to populate local caches.
                    rlAssertGrep "summary: 3 preparations applied" $rlRun_LOG
                else
                    rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
                fi
            rlPhaseEnd
        fi

        rlPhaseStartTest "$phase_prefix Install existing and invalid packages (plan)"
            rlRun -s "$tmt plan --name /missing" 2

            rlAssertGrep "package manager: $package_manager" $rlRun_LOG

            if is_centos_7 "$image"; then
                rlAssertGrep "out: no package provides tree-but-spelled-wrong" $rlRun_LOG

            elif is_ostree "$image"; then
                rlAssertGrep "err: error: Packages not found: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_coreos "$image"; then
                rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_rawhide "$image"; then
                if [ "$PROVISION_HOW" = "virtual" ]; then
                    rlAssertGrep "err: Error: Unable to find a match: tree-but-spelled-wrong" $rlRun_LOG
                else
                    rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG
                fi

            elif is_ubuntu "$image"; then
                rlAssertGrep "err: E: Unable to locate package tree-but-spelled-wrong" $rlRun_LOG

            elif is_alpine "$image"; then
                rlAssertGrep "err:   tree-but-spelled-wrong (no such package)" $rlRun_LOG

            else
                rlAssertGrep "err: Error: Unable to find a match: tree-but-spelled-wrong" $rlRun_LOG
            fi
        rlPhaseEnd

        rlPhaseStartTest "$phase_prefix Install existing and invalid packages (CLI)"
            rlRun -s "$tmt --insert --how install --package tree-but-spelled-wrong --package diffutils plan --name /empty" 2

            rlAssertGrep "package manager: $package_manager" $rlRun_LOG

            if is_centos_7 "$image"; then
                rlAssertGrep "out: no package provides tree-but-spelled-wrong" $rlRun_LOG

            elif is_ostree "$image"; then
                rlAssertGrep "err: error: Packages not found: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_coreos "$image"; then
                rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_rawhide "$image"; then
                if [ "$PROVISION_HOW" = "virtual" ]; then
                    rlAssertGrep "err: Error: Unable to find a match: tree-but-spelled-wrong" $rlRun_LOG
                else
                    rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG
                fi

            elif is_ubuntu "$image"; then
                rlAssertGrep "err: E: Unable to locate package tree-but-spelled-wrong" $rlRun_LOG

            elif is_alpine "$image"; then
                rlAssertGrep "err:   tree-but-spelled-wrong (no such package)" $rlRun_LOG

            else
                rlAssertGrep "err: Error: Unable to find a match: tree-but-spelled-wrong" $rlRun_LOG
            fi
        rlPhaseEnd

        # TODO: at least copr is RH-specific, but package name escaping and debuginfo should be
        # possible to extend to other distros.
        if (is_fedora "$image" && ! is_fedora_coreos "$image") || is_centos "$image" || is_ubi "$image"; then
            if ! is_centos_7 "$image"; then
                rlPhaseStartTest "$phase_prefix Just enable copr"
                    rlRun "$tmt execute plan --name copr"
                rlPhaseEnd

                rlPhaseStartTest "$phase_prefix Exclude selected packages"
                    rlRun "$tmt execute plan --name exclude"
                rlPhaseEnd
            fi

            rlPhaseStartTest "$phase_prefix Escape package names"
                rlRun "$tmt execute plan --name escape"
            rlPhaseEnd

            if is_centos_7 "$image"; then
                rlPhaseStartTest "$phase_prefix Install from epel7 copr"
                    rlRun "$tmt execute plan --name epel7"
                rlPhaseEnd
            fi

            if is_centos_stream_8 "$image"; then
                rlPhaseStartTest "$phase_prefix Install remote packages"
                    rlRun "$tmt execute plan --name epel8-remote"
                rlPhaseEnd
            fi

            rlPhaseStartTest "$phase_prefix Install debuginfo packages"
                rlRun "$tmt execute plan --name debuginfo"
            rlPhaseEnd
        fi
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
