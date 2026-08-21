#!/bin/bash
set -eu
workdir="${TMT_TEST_DATA:-${TMPDIR:-/tmp}/tmt-synthetic-write}"
mkdir -p "${workdir}/synthetic-write"
for index in 1 2 3 4 5; do
    head -c 4096 /dev/urandom | base64 > "${workdir}/synthetic-write/blob-${index}.dat"
done
