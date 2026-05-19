#!/bin/bash
# Build local RPM repos from per-repo spec directories and collect
# pre-install RPM files.  Run this on the outer container before
# launching inner tmt runs.

set -ex
shopt -s nullglob

# Directories that become DNF repos (get createrepo metadata).
REPO_DIRS=(system tc01 tc02 tc03 tc04 tc05 tc06 tc07 tc08 tc09)

for repo_dir in "${REPO_DIRS[@]}"; do
    [ -d "$repo_dir" ] || continue
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

# preinstall/ — raw RPM files used for rpm -i --force pre-installation.
# No createrepo needed; these are not a DNF repo.
pushd preinstall
build_dir=$(mktemp -d)
for spec in *.spec; do
    rpmbuild --define "_topdir $build_dir" -bb "$spec"
done
find "$build_dir/RPMS" -name "*.rpm" -exec cp {} . \;
rm -rf "$build_dir"
popd
