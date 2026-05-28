#!/bin/bash
# Common helper functions for artifact provider tests

LIB_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")

setup_distro_environment() {
    rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
    rlRun "IMAGE_MODE=${IMAGE_MODE:-no}"
    if [ "$IMAGE_MODE" = "yes" ]; then
        rlDie "Image mode is not covered"
    elif [ "$PROVISION_HOW" = "container" ]; then
        rlRun "IMAGES='$TEST_CONTAINER_IMAGES'"
        build_container_images
    elif [ "$PROVISION_HOW" = "virtual" ]; then
        rlRun "IMAGES='$TEST_VIRTUAL_IMAGES'"
    else
        rlRun "IMAGES="
    fi
}

function build_rpms() {
    for rpm_dir in $LIB_DIR/../rpms/*; do
        build_rpm $(basename $rpm_dir)
    done
}

function build_rpm() {
    local rpm_dir=$LIB_DIR/../rpms/$1
    if [[ ! -d "$rpm_dir/build" ]]; then
        rlRun "pushd $rpm_dir"
        rlRun "rpmbuild --define='_topdir build' -bb *.spec" 0 "Build rpm"
        rlRun "cp build/RPMS/*/* ./" 0 "Move rpms next to spec file"
        rlRun "popd"
    fi
}

# Get koji build ID from package name (fetch latest for tag, with inheritance)
#
# Usage:
#   get_koji_build_id "make" "f43"
#   echo "$KOJI_BUILD_ID"
#
# Arguments:
#   $1 - package name (e.g., "make")
#   $2 - koji tag (e.g., "f43")
#
# Sets:
#   KOJI_BUILD_ID - the build ID on success
#
# On failure, calls rlDie to abort the test.
#
# Note: This function uses rlRun for logging. The build ID is stored
# in the KOJI_BUILD_ID global variable (not printed to stdout) to
# avoid capturing rlRun output when using command substitution.
#
# The --inherit flag is used to also search parent tags (e.g., epel10.3
# inherits from epel10), ensuring builds inherited from parent tags are found.
#
get_koji_build_id() {
    local package="$1"
    local tag="$2"
    unset KOJI_BUILD_ID  # Clear any previous value

    # Get the latest tagged build for the package (including inherited tags)
    # Output format: "make-4.4.1-10.fc42    f42    releng"
    rlRun -s "koji list-tagged --latest --inherit $tag $package" 0 "Get the latest $package build (with inheritance)"

    # The NVR should be the first word in the last line
    if [[ ! "$(tail -1 $rlRun_LOG)" =~ ^([^[:space:]]+) ]]; then
        rlDie "Failed to get koji build ID: NVR regex failed for '$package' tag '$tag'"
    fi
    local nvr="${BASH_REMATCH[1]}"
    rlLogInfo "Found NVR: $nvr"

    # Get the build info for the NVR
    # Output format: "BUILD: make-4.4.1-10.fc42 [2625600]"
    rlRun -s "koji buildinfo $nvr" 0 "Get the build info for $nvr"

    # The build ID should be in square brackets of the first line
    if [[ ! "$(head -1 $rlRun_LOG)" =~ ^BUILD:[[:space:]]*[^[:space:]]+[[:space:]]*\[([[:digit:]]+)\] ]]; then
        rlDie "Failed to get koji build ID: Build ID regex failed for NVR '$nvr'"
    fi
    KOJI_BUILD_ID="${BASH_REMATCH[1]}"
    rlLogInfo "Found build ID: $KOJI_BUILD_ID"
}

# Get koji NVR from package name (fetch latest for tag)
#
# Usage:
#   get_koji_nvr "make" "f43"
#   echo "$KOJI_NVR"
#
#   get_koji_nvr "tree" "c10s" "stream"
#   echo "$KOJI_NVR"
#
# Arguments:
#   $1 - package name (e.g., "make")
#   $2 - koji tag (e.g., "f43")
#   $3 - optional profile (e.g., "stream")
#
# Sets:
#   KOJI_NVR - the NVR on success
#
# On failure, calls rlDie to abort the test.
#
# Note: This function uses rlRun for logging. The NVR is stored
# in the KOJI_NVR global variable (not printed to stdout) to
# avoid capturing rlRun output when using command substitution.
#
get_koji_nvr() {
    local package="$1"
    local tag="$2"
    local profile="$3"
    unset KOJI_NVR  # Clear any previous value

    local profile_option=""
    [ -n "$profile" ] && profile_option="--profile $profile"

    # Get the latest tagged build for the package
    # Output format: "make-4.4.1-10.fc42    f42    releng"
    rlRun -s "koji $profile_option list-tagged --latest $tag $package" 0 "Get the latest $package build"

    # The NVR should be the first word in the last line
    if [[ ! "$(tail -1 $rlRun_LOG)" =~ ^([^[:space:]]+) ]]; then
        rlDie "Failed to get koji NVR: NVR regex failed for '$package' tag '$tag'"
    fi
    KOJI_NVR="${BASH_REMATCH[1]}"
    rlLogInfo "Found NVR: $KOJI_NVR"
}
