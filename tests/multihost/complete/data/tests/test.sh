#!/bin/sh -e

echo "In a test!"

for envvar in $(compgen -A variable | egrep 'TMT' | sort); do
    echo "$envvar=${!envvar}"
done

sed -e 's/^/topology-sh: /' "$TMT_TOPOLOGY_BASH"
sed -e 's/^/topology-yaml: /' "$TMT_TOPOLOGY_YAML"
