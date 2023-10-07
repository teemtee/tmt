#!/bin/bash

FILE=$(readlink -f $BASH_SOURCE)
NAME=$(basename $FILE)
CDIR=$(dirname $FILE)
TMPDIR=${TMPDIR:-"/tmp"}

function check_epel_enabled
{
    rpm -q "epel-release"
    return $?
}

check_epel_enabled
exit $?
