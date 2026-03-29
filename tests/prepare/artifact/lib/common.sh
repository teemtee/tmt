#!/bin/bash
# Common helper functions for artifact provider tests

# Setup distro test environment
#
# This function checks the distro, sets up the release version
# and image_name variables, and builds the container image.
#
# Sets the following global variables:
#   fedora_release - The Fedora release version (e.g., "43")
#   image_name - The container image name (e.g., "fedora/43:latest")
#
# Usage: setup_distro_environment
#
setup_distro_environment() {
    if ! rlIsFedora; then
        rlDie "Test requires Fedora"
    fi

    # TODO: Temporary hardcoded release - should be taken from function input
    fedora_release=43
    image_name="fedora/${fedora_release}:latest"
    build_container_image "$image_name"
}

# Setup CentOS test environment
#
# Sets the following global variables:
#   centos_release - The CentOS Stream release version (e.g., "10")
#   epel_tag - The EPEL koji tag (e.g., "epel10.3" or "epel9")
#   image_name - The container image name (e.g., "centos/stream10/upstream:latest")
#
# Usage: setup_centos_environment
#
setup_centos_environment() {
    if ! rlIsCentOS; then
        rlDie "Test requires CentOS"
    fi

    centos_release=$(rlGetDistroRelease)
    image_name="centos/stream${centos_release}/upstream:latest"
    build_container_image "$image_name"

    # For CentOS 10+, packages are tagged under epelX.Y (e.g., epel10.3).
    # For CentOS 9 and earlier, the plain epelX tag is used (e.g., epel9).
    epel_tag=$(koji list-tags 2>/dev/null | grep -E "^epel${centos_release}\.[0-9]+$" | sort -V | tail -1)
    epel_tag="${epel_tag:-epel${centos_release}}"
}

# Get koji build ID from package name (fetch latest for tag)
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
get_koji_build_id() {
    local package="$1"
    local tag="$2"
    unset KOJI_BUILD_ID  # Clear any previous value

    # Get the latest tagged build for the package
    # Output format: "make-4.4.1-10.fc42    f42    releng"
    rlRun -s "koji list-tagged --latest $tag $package" 0 "Get the latest $package build"

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
