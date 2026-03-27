#!/bin/bash
# Common helper functions for artifact provider tests

# Setup distro test environment
#
# This function checks the distro, sets up the release version
# and image_name variables, and builds the container image.
#
# Sets the following global variables:
#   release - The distro release version (e.g., "43" for Fedora, "10" for CentOS)
#   fedora_release - The Fedora release version for koji queries (e.g., "43")
#   image_name - The container image name (e.g., "fedora/43:latest")
#
# Usage: setup_distro_environment
#
setup_distro_environment() {
    release=$(grep VERSION_ID /etc/os-release | cut -d= -f2 | tr -d '"')

    if rlIsFedora; then
        fedora_release="$release"
        image_name="fedora/${release}:latest"
    elif rlIsCentOS; then
        # For koji queries, use Fedora release (packages are in Fedora koji)
        fedora_release="${FEDORA_RELEASE:-43}"
        image_name="centos/stream${release}/upstream:latest"
    else
        rlDie "Test requires Fedora or CentOS"
    fi
    build_container_image "$image_name"
}

# Get koji build ID from package name (fetch latest for tag)
#
# Usage:
#   get_koji_build_id "centpkg" "f43"
#   echo "$KOJI_BUILD_ID"
#
#   get_koji_build_id "centpkg" "c10s" "stream"
#   echo "$KOJI_BUILD_ID"
#
# Arguments:
#   $1 - package name (e.g., "centpkg")
#   $2 - koji tag (e.g., "f43")
#   $3 - optional profile (e.g., "stream")
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
    local profile="$3"
    unset KOJI_BUILD_ID  # Clear any previous value

    # Get the latest tagged build for the package
    # Output format: "centpkg-0.10.3-1.fc43    f43    releng"
    rlRun -s "koji ${profile:+--profile $profile} list-tagged --latest $tag $package" 0 "Get the latest $package build"

    # The NVR should be the first word in the last line
    if [[ ! "$(tail -1 $rlRun_LOG)" =~ ^([^[:space:]]+) ]]; then
        rlDie "Failed to get koji build ID: NVR regex failed for '$package' tag '$tag'"
    fi
    local nvr="${BASH_REMATCH[1]}"
    rlLogInfo "Found NVR: $nvr"

    # Get the build info for the NVR
    # Output format: "BUILD: centpkg-0.10.3-1.fc43 [2625600]"
    rlRun -s "koji ${profile:+--profile $profile} buildinfo $nvr" 0 "Get the build info for $nvr"

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

    # Get the latest tagged build for the package
    # Output format: "make-4.4.1-10.fc42    f42    releng"
    rlRun -s "koji ${profile:+--profile $profile} list-tagged --latest $tag $package" 0 "Get the latest $package build"

    # The NVR should be the first word in the last line
    if [[ ! "$(tail -1 $rlRun_LOG)" =~ ^([^[:space:]]+) ]]; then
        rlDie "Failed to get koji NVR: NVR regex failed for '$package' tag '$tag'"
    fi
    KOJI_NVR="${BASH_REMATCH[1]}"
    rlLogInfo "Found NVR: $KOJI_NVR"
}
