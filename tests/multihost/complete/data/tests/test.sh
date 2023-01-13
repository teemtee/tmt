#!/bin/sh -e

echo "In a test!"

for envvar in $(compgen -A variable | egrep 'SERVERS|TMT' | sort); do
    echo "$envvar=${!envvar}"
done
