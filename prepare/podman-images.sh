#!/bin/bash
#
# Fetch dnf cache for the default set of container images
# (or custom set provided in the IMAGES environment variable).
# Retry three times to prevent random network issues.

IMAGES=${IMAGES:-fedora centos:stream9}

TOTAL=0
SUCCESSFULL=0

set -x

for image in $IMAGES; do
    TOTAL=$((TOTAL + 1))

    for attempt in {1..3}; do
        echo "Fetch container image '$image' attempt $attempt."

        # Fetch the image, run `dnf makecache`, commit the image
        podman rm -f fresh --time 0 &&
        podman run -itd --name fresh --pull always "$image" &&
        podman exec fresh dnf makecache &&
        podman commit fresh "$image" &&

        # Count success and break or sleep a bit before the next attempt
        SUCCESSFULL=$((SUCCESSFULL + 1)) && break
        sleep 3
    done
done

set +x

echo "Total: $TOTAL"
echo "Successfull: $SUCCESSFULL"
[[ "$SUCCESSFULL" == "$TOTAL" ]] && exit 0 || exit 1
