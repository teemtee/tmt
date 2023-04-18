#!/bin/sh -eux

echo "In a test!"

for envvar in $(compgen -A variable | grep TMT | sort); do
    echo "$envvar=${!envvar}"
done
