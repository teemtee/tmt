#!/bin/bash
# Common helper functions for artifact provider tests

# Get koji build ID from package name (fetch latest for tag)
get_koji_build_id() {
    local package="$1"
    local tag="$2"
    local nvr build_id

    nvr=$(koji list-tagged --latest "$tag" "$package" 2>/dev/null | tail -1 | awk '{print $1}')
    if [ -z "$nvr" ]; then
        return 1
    fi

    build_id=$(koji buildinfo "$nvr" 2>/dev/null | head -1 | grep -oP '\[\K[0-9]+(?=\])')
    if [ -z "$build_id" ]; then
        return 1
    fi

    echo "$build_id"
}
