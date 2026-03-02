#!/bin/bash
# Build local RPM repos from per-repo spec directories.
# For each subdirectory containing .spec files, builds binary RPMs
# and runs createrepo_c in-place.

set -ex
shopt -s nullglob

for repo_dir in */; do
    pushd "$repo_dir"
    build_dir=$(mktemp -d)
    for spec in *.spec; do
        rpmbuild --define "_topdir $build_dir" -bb "$spec"
    done
    find "$build_dir/RPMS" -name "*.rpm" -exec cp {} . \;
    rm -rf "$build_dir"
    createrepo .
    popd
done
