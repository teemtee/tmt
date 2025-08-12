#!/bin/bash
source "$TMT_TOPOLOGY_BASH"

if [ "${TMT_GUEST["name"]}" == "client-2" ]; then
    tmt-report-result D SKIP
fi
