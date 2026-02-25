#!/bin/bash
# One-time script to build SRPMs from the spec files and commit them.
# Run this whenever the spec files change, then commit data/srpms/.
#
# Usage:
#   ./build_srpms.sh
#   git add data/srpms/*.src.rpm
#   git commit -m "Update committed SRPMs"

set -ex

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SRPM_DIR="$SCRIPT_DIR/../data/srpms"

mkdir -p "$SRPM_DIR"

mock --buildsrpm --spec "$SCRIPT_DIR/v1.spec" --sources "$SCRIPT_DIR/" \
    --resultdir "$SRPM_DIR" --enable-network
mock --buildsrpm --spec "$SCRIPT_DIR/v2.spec" --sources "$SCRIPT_DIR/" \
    --resultdir "$SRPM_DIR" --enable-network

# This is done to speed up the tests
echo "SRPMs staged in $SRPM_DIR — commit them with:"
echo "  git add data/srpms/*.src.rpm && git commit"
