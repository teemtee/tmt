#!/bin/bash
#
# Build the tmt container images for proxy
#
set -e

# Directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Root of the tmt repository
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Registry and tag configuration
REGISTRY=${REGISTRY:-"quay.io"}
NAMESPACE=${NAMESPACE:-"teemtee"}
TAG=${TAG:-"latest"}

# Define image names
MINI_IMAGE="${REGISTRY}/${NAMESPACE}/tmt:${TAG}"
FULL_IMAGE="${REGISTRY}/${NAMESPACE}/tmt:${TAG}-full"

# Build the container images
cd "${REPO_ROOT}"

echo "Building tmt-mini container image..."
podman build -t "${MINI_IMAGE}" -f containers/Containerfile --build-arg VARIANT=tmt .

echo "Building tmt-full container image..."
podman build -t "${FULL_IMAGE}" -f containers/Containerfile --build-arg VARIANT=tmt+all .

echo
echo "Testing images..."
echo "Mini variant:"
podman run --rm "${MINI_IMAGE}" --version
echo
echo "Full variant:"
podman run --rm "${FULL_IMAGE}" --version

echo
echo "Images built successfully:"
echo "  ${MINI_IMAGE}"
echo "  ${FULL_IMAGE}"
echo
echo "To use the container images directly:"
echo "  podman run --rm -it -v \$(pwd):/tmt -w /tmt ${MINI_IMAGE} run"
echo "  podman run --rm -it -v \$(pwd):/tmt -w /tmt ${FULL_IMAGE} run"
echo
echo "To build the RPM packages:"
echo "  rpmbuild -ba ${SCRIPT_DIR}/tmt-container.spec \\"
echo "           --define \"_sourcedir ${SCRIPT_DIR}\" \\"
echo "           --define \"_rpmdir $(pwd)/rpmbuild\""
echo
echo "To install the proxy script directly:"
echo "  sudo install -m 755 ${SCRIPT_DIR}/tmt-proxy.sh /usr/bin/tmt"
