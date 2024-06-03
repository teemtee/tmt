#!/bin/bash

#
# A couple of helper functions to interface between tests and `make`
# targets building test images.
#

TEST_IMAGE_PREFIX="localhost/tmt/tests/container"

# Directory where the top-level Makefile lives. It might be possible to
# rely on tmt, but sometimes one might want to run a test directly,
# without tmt orchestrating it.
#
# "Source" of this script -> its absolute path -> dirname -> one level above `tests/`
_MAKEFILE_DIR="$(dirname $(readlink -f ${BASH_SOURCE[0]}))/.."

function build_container_image () {
    # Try several times to build the container
    # https://github.com/teemtee/tmt/issues/2063
    build="make -C $_MAKEFILE_DIR images-tests/tmt/tests/container/$1"
    rlRun "rlWaitForCmd '$build' -m 5 -d 5 -t 3600" || rlDie "Unable to prepare the image"
}


function build_container_images () {
    # Try several times to build the container
    # https://github.com/teemtee/tmt/issues/2063
    build="make -C $_MAKEFILE_DIR images-tests"
    rlRun "rlWaitForCmd '$build' -m 5 -d 5 -t 3600" || rlDie "Unable to prepare the images"
}
