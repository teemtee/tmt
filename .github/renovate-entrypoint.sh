#!/bin/bash

# See https://github.com/renovatebot/github-action#docker-cmd-file

apt update
apt install -y \
    libvirt-dev \
    libkrb5-dev \
    libpq-dev

runuser -u ubuntu renovate
