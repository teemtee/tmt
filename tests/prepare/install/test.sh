#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

function fetch_downloaded_packages () {
    in_subdirectory="$2"

    if [ ! -e $package_cache/tree.rpm ]; then
        # For some reason, this command will get stuck in rlRun...
        container_id="$(podman run -d $1 sleep 3600)"

        rlRun "podman exec $container_id bash -c \"set -x; \
                                                    dnf install -y 'dnf-command(download)' \
                                                    && dnf download --destdir /tmp tree diffutils \
                                                    && mv /tmp/tree*.rpm /tmp/tree.rpm \
                                                    && mv /tmp/diffutils*.rpm /tmp/diffutils.rpm\""
        rlRun "podman cp $container_id:/tmp/tree.rpm $package_cache/"
        rlRun "podman cp $container_id:/tmp/diffutils.rpm $package_cache/"
        rlRun "podman kill $container_id"
        rlRun "podman rm $container_id"
    fi

    if [ -z "$in_subdirectory" ]; then
        rlRun "cp $package_cache/tree.rpm ./"
        rlRun "cp $package_cache/diffutils.rpm ./"
    else
        rlRun "mkdir -p ./downloaded-rpms"
        rlRun "cp $package_cache/tree.rpm ./downloaded-rpms"
        rlRun "cp $package_cache/diffutils.rpm ./downloaded-rpms"
    fi
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        if [ "$PROVISION_HOW" = "container" ]; then
            rlRun "IMAGES='$TEST_CONTAINER_IMAGES'"

            build_container_images

        elif [ "$PROVISION_HOW" = "virtual" ]; then
            rlRun "IMAGES='$TEST_VIRTUAL_IMAGES'"

        else
            rlRun "IMAGES="
        fi

        rlRun "package_cache=\$(mktemp -d)" 0 "Create cache directory for downloaded packages"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"

        rlRun "export TMT_BOOT_TIMEOUT=300"
        rlRun "export TMT_CONNECT_TIMEOUT=300"
    rlPhaseEnd

    while IFS= read -r image; do
        phase_prefix="$(test_phase_prefix $image)"

        rlPhaseStartTest "$phase_prefix Prepare runtime"
            [ "$PROVISION_HOW" = "container" ] && rlRun "podman images $image"

            if is_fedora_rawhide "$image"; then
                rlRun "distro=fedora-rawhide"
                rlRun "package_manager=dnf5"

            elif is_fedora_41 "$image"; then
                rlRun "distro=fedora-41"
                rlRun "package_manager=dnf5"

            elif is_fedora_40 "$image"; then
                rlRun "distro=fedora-40"
                rlRun "package_manager=dnf"

            elif is_fedora_39 "$image"; then
                rlRun "distro=fedora-39"
                rlRun "package_manager=dnf"

            elif is_centos_stream_9 "$image"; then
                rlRun "distro=centos-stream-9"
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

            elif is_ubi_8 "$image"; then
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
        rlPhaseStartTest "$phase_prefix Install existing packages (plan)"
            rlRun -s "$tmt plan --name /existing"

            rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

            if is_ubuntu "$image"; then
                # Runs 1 extra phase, to populate local caches.
                rlAssertGrep "summary: 3 preparations applied" $rlRun_LOG
            else
                rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
            fi
        rlPhaseEnd

        rlPhaseStartTest "$phase_prefix Install existing packages (CLI)"
            if is_ubi "$image"; then
                rlRun -s "$tmt --insert --how install --package dconf --package libpng plan --name /empty"
            else
                rlRun -s "$tmt --insert --how install --package tree --package diffutils plan --name /empty"
            fi

            rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

            if is_ubuntu "$image"; then
                # Runs 1 extra phase, to populate local caches.
                rlAssertGrep "summary: 3 preparations applied" $rlRun_LOG
            else
                rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
            fi
        rlPhaseEnd

        if rlIsFedora 39 && is_fedora_39 "$image"; then
            rlPhaseStartTest "$phase_prefix Install downloaded packages from current directory (plan)"
                fetch_downloaded_packages "$image"

                rlRun -s "$tmt plan --name /downloaded/in-cwd"

                rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

                rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
            rlPhaseEnd

            rlPhaseStartTest "$phase_prefix Install downloaded packages from current directory (CLI)"
                fetch_downloaded_packages "$image"

                rlRun -s "$tmt prepare --insert --how install --package tree*.rpm --package diffutils*.rpm plan --name /empty"

                rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

                rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
            rlPhaseEnd

            rlPhaseStartTest "$phase_prefix Install downloaded packages from subdirectory (plan)"
                fetch_downloaded_packages "$image" "yes"

                rlRun -s "$tmt plan --name /downloaded/in-subdirectory"

                rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

                rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
            rlPhaseEnd

            rlPhaseStartTest "$phase_prefix Install downloaded packages from subdirectory (CLI)"
                fetch_downloaded_packages "$image" "yes"

                rlRun -s "$tmt prepare --insert --how install --package downloaded-rpms/tree.rpm --package downloaded-rpms/diffutils.rpm plan --name /empty"

                rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

                rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
            rlPhaseEnd

            rlPhaseStartTest "$phase_prefix Install downloaded directory (plan)"
                fetch_downloaded_packages "$image" "yes"

                rlRun -s "$tmt plan --name /downloaded/as-directory"

                rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

                rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
            rlPhaseEnd

            rlPhaseStartTest "$phase_prefix Install downloaded directory (CLI)"
                fetch_downloaded_packages "$image" "yes"

                rlRun -s "$tmt prepare --insert --how install --directory downloaded-rpms plan --name /empty"

                rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

                rlAssertGrep "summary: 2 preparations applied" $rlRun_LOG
            rlPhaseEnd
        fi

        rlPhaseStartTest "$phase_prefix Install existing and invalid packages (plan)"
            rlRun -s "$tmt plan --name /missing" 2

            rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

            if is_centos_7 "$image"; then
                rlAssertGrep "out: no package provides tree-but-spelled-wrong" $rlRun_LOG

            elif is_ostree "$image"; then
                rlAssertGrep "err: error: Packages not found: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_coreos "$image"; then
                rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_rawhide "$image"; then
                rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_41 "$image"; then
                rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_40 "$image"; then
                rlAssertGrep "err: Error: Unable to find a match: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_39 "$image"; then
                rlAssertGrep "err: Error: Unable to find a match: tree-but-spelled-wrong" $rlRun_LOG

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

            rlAssertGrep "package manager: $package_manager$" $rlRun_LOG

            if is_centos_7 "$image"; then
                rlAssertGrep "out: no package provides tree-but-spelled-wrong" $rlRun_LOG

            elif is_ostree "$image"; then
                rlAssertGrep "err: error: Packages not found: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_coreos "$image"; then
                rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_rawhide "$image"; then
                rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_41 "$image"; then
                rlAssertGrep "err: No match for argument: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_40 "$image"; then
                rlAssertGrep "err: Error: Unable to find a match: tree-but-spelled-wrong" $rlRun_LOG

            elif is_fedora_39 "$image"; then
                rlAssertGrep "err: Error: Unable to find a match: tree-but-spelled-wrong" $rlRun_LOG

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

            if is_centos_stream_9 "$image"; then
                rlPhaseStartTest "$phase_prefix Install remote packages"
                    rlRun "$tmt execute plan --name epel9-remote"
                rlPhaseEnd
            fi

            if is_ubi_8 "$image"; then
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
        rlRun "rm -r $package_cache" 0 "Remove package cache directory"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
