#!/bin/bash
set -ex

for package in cowsay figlet boxes fortune-mod; do
    # verify the package is installed
    rpm -q "$package"
    # verify package came from the tmt-artifact-shared repository
    dnf info --installed "$package" | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
done
