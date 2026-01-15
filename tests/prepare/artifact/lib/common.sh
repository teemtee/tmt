#!/bin/bash
# Common helper functions for artifact provider tests

# Setup Fedora test environment
#
# This function checks if running on Fedora, sets up the fedora_release
# and image_name variables, and builds the container image.
#
# Sets the following global variables:
#   fedora_release - The Fedora release version (e.g., "43")
#   image_name - The container image name (e.g., "fedora/43:latest")
#
# Usage: setup_fedora_environment
#
setup_fedora_environment() {
    if ! rlIsFedora; then
        rlDie "Test requires Fedora"
    fi

    fedora_release=43
    image_name="fedora/${fedora_release}:latest"
    build_container_image "$image_name"
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
# Returns:
#   0 on success, 1 on failure
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
        rlLogWarning "Package NVR regex failed for '$package' tag '$tag'"
        return 1
    fi
    local nvr="${BASH_REMATCH[1]}"
    rlLogInfo "Found NVR: $nvr"

    # Get the build info for the NVR
    # Output format: "BUILD: make-4.4.1-10.fc42 [2625600]"
    rlRun -s "koji buildinfo $nvr" 0 "Get the build info for $nvr"

    # The build ID should be in square brackets of the first line
    if [[ ! "$(head -1 $rlRun_LOG)" =~ ^BUILD:[[:space:]]*[^[:space:]]+[[:space:]]*\[([[:digit:]]+)\] ]]; then
        rlLogWarning "Build ID regex failed for NVR '$nvr'"
        return 1
    fi
    KOJI_BUILD_ID="${BASH_REMATCH[1]}"
    rlLogInfo "Found build ID: $KOJI_BUILD_ID"
}
