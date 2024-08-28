#!/bin/bash

#
# A couple of helper functions to interface between tests and `make`
# targets building test images.
#

# A preix shared by all images built for tests.
TEST_IMAGE_PREFIX="localhost/tmt/tests/container"

# Directory where the top-level Makefile lives. It might be possible to
# rely on tmt, but sometimes one might want to run a test directly,
# without tmt orchestrating it.
#
# "Source" of this script -> its absolute path -> dirname -> one level above `tests/`
_MAKEFILE_DIR="$(dirname $(readlink -f ${BASH_SOURCE[0]}))/.."

# Basic set of container images to test on
#
# It does not contain "unprivileged" images.
TEST_CONTAINER_IMAGES="${TEST_CONTAINER_IMAGES:-$TEST_IMAGE_PREFIX/alpine:latest
$TEST_IMAGE_PREFIX/centos/7/upstream:latest
$TEST_IMAGE_PREFIX/centos/stream9/upstream:latest
$TEST_IMAGE_PREFIX/fedora/39/upstream:latest
$TEST_IMAGE_PREFIX/fedora/40/upstream:latest
$TEST_IMAGE_PREFIX/fedora/41/upstream:latest
$TEST_IMAGE_PREFIX/fedora/rawhide/upstream:latest
$TEST_IMAGE_PREFIX/fedora/coreos:stable
$TEST_IMAGE_PREFIX/fedora/coreos/ostree:stable
$TEST_IMAGE_PREFIX/ubi/8/upstream:latest
$TEST_IMAGE_PREFIX/ubuntu/22.04/upstream:latest}"

# Basic set of virtual images to test on.
#
# Enable Alpine
# TODO: enable Ubuntu
# TODO: enable centos-7 again with modified repo files
TEST_VIRTUAL_IMAGES="${TEST_VIRTUAL_IMAGES:-centos-stream-9
fedora-39
fedora-40
fedora-41
fedora-rawhide
fedora-coreos}"

# A couple of "is image this?" helpers, to simplify conditions.
function is_fedora_rawhide () {
    [[ "$1" =~ ^.*fedora/rawhide[:/].* ]] && return 0
    [[ "$1" = "fedora-rawhide" ]] && return 0

    return 1
}

function is_fedora_41 () {
    [[ "$1" =~ ^.*fedora/41[:/].* ]] && return 0
    [[ "$1" = "fedora-41" ]] && return 0

    return 1
}

function is_fedora_40 () {
    [[ "$1" =~ ^.*fedora/40[:/].* ]] && return 0
    [[ "$1" = "fedora-40" ]] && return 0

    return 1
}

function is_fedora_39 () {
    [[ "$1" =~ ^.*fedora/39[:/].* ]] && return 0
    [[ "$1" = "fedora-39" ]] && return 0

    return 1
}

function is_centos_stream_9 () {
    [[ "$1" =~ ^.*centos/stream9[:/].* ]] && return 0
    [[ "$1" = "centos-stream-9" ]] && return 0

    return 1
}

function is_centos_7 () {
    [[ "$1" =~ ^.*centos/7[:/].* ]] && return 0
    [[ "$1" = "centos-7" ]] && return 0

    return 1
}

function is_ubuntu () {
    [[ "$1" =~ ^.*ubuntu/.* ]] && return 0
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

function is_ubi_8 () {
    [[ "$1" =~ ^.*ubi/8.* ]] && return 0 || return 1
}

function test_phase_prefix () {
    if [ "$PROVISION_HOW" = "local" ]; then
        echo "[$PROVISION_HOW]"
    else
        echo "[$PROVISION_HOW / $(echo $1 | sed "s|$TEST_IMAGE_PREFIX/||")]"
    fi
}

# Building of container images
function build_container_image () {
    if [ "$PROVISION_HOW" != "container" ]; then
        rlLogInfo "Skipping the build of $1 container image because of PROVISION_HOW=$PROVISION_HOW"
        return
    fi

    # Try several times to build the container
    # https://github.com/teemtee/tmt/issues/2063
    build="make -C $_MAKEFILE_DIR images-tests/tmt/tests/container/$1"
    rlWaitForCmd "$build" -m 5 -d 5 -t 3600 || rlDie "Unable to prepare the image"
}


function build_container_images () {
    if [ "$PROVISION_HOW" != "container" ] && [ "$1" != "--force" ]; then
        rlLogInfo "Skipping the build of container images because of PROVISION_HOW=$PROVISION_HOW"
        return
    fi

    # Try several times to build the container
    # https://github.com/teemtee/tmt/issues/2063
    build="make -C $_MAKEFILE_DIR images-tests"
    rlWaitForCmd "$build" -m 5 -d 5 -t 3600 || rlDie "Unable to prepare the images"
}
