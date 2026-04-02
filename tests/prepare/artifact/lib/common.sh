#!/bin/bash
# Common helper functions for artifact provider tests

# Setup distro test environment
#
# This function checks the distro, sets up the release version,
# image_name, and koji_tag variables, and builds the container image.
#
# Sets the following global variables:
#   release - The distro release version (e.g., "43" for Fedora, "10" for CentOS)
#   image_name - The container image name (e.g., "fedora/43:latest")
#   koji_tag - The koji tag for querying builds (e.g., "f43" for Fedora, "epel10" for CentOS)
#
# Usage: setup_distro_environment
#
setup_distro_environment() {
    if rlIsFedora; then
        release=$(rlGetDistroRelease)
        koji_tag="f${release}"
        distro="fedora-${release}"
        # FIXME: Rawhide reports numeric release identifiers (e.g., "45") but versioned
        # container targets (fedora/45/*) don't exist yet. Mapping fedora/45 to rawhide
        # as a workaround until https://github.com/teemtee/tmt/pull/4775 is merged.
        if grep -qi "rawhide" /etc/os-release; then
            image_name="fedora/rawhide:latest"
        else
            image_name="fedora/${release}:latest"
        fi
    elif rlIsCentOS; then
        release=$(rlGetDistroRelease)
        image_name="centos/stream${release}/upstream:latest"
        koji_tag="epel${release}"
        distro="centos-stream-${release}"
    else
        rlDie "Test requires Fedora or CentOS"
    fi
    build_container_image "$image_name"
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
