#!/usr/bin/env bash

set -eux

. "$TMT_TOPOLOGY_BASH"
# verify that TOPLOGY to be defined to be able to run the tests.
test -z "${TMT_ROLES[server]}" && exit 125

SERVER=${TMT_GUESTS[${TMT_ROLES[server]}.hostname]}
redis-cli -h $SERVER get key | grep value1
