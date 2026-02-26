#!/bin/bash
# Build local RPM repos from per-repo spec directories.
# For each subdirectory containing .spec files, builds SRPMs and binary RPMs,
# then creates a repo in-place at /tmp/nvr-test/<dirname>.

set -ex

REPO_BASE="/tmp/nvr-test"

for repo_dir in */; do
    repo="${repo_dir%/}"
    mkdir -p "$REPO_BASE/$repo"
    pushd "$repo_dir"
    build_dir=$(mktemp -d)
    for spec in *.spec; do
        rpmbuild --define "_topdir $build_dir" -bs "$spec"
    done
    for srpm in "$build_dir"/SRPMS/*.src.rpm; do
        rpmbuild --define "_topdir $build_dir" --rebuild "$srpm"
    done
    cp "$build_dir"/RPMS/noarch/*.rpm "$REPO_BASE/$repo/"
    rm -rf "$build_dir"
    createrepo_c "$REPO_BASE/$repo"
    popd
done
