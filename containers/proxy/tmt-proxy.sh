#!/bin/bash
#
# tmt proxy script - transparently runs tmt commands in container
#

# Default container image ("mini" variant)
TMT_IMAGE="quay.io/teemtee/tmt:latest"

# Check if the full variant is requested via environment variable
if [[ "${TMT_VARIANT}" == "full" ]]; then
    TMT_IMAGE="quay.io/teemtee/tmt:latest-full"
fi

# Override image via environment variable if set
if [[ -n "${TMT_CONTAINER_IMAGE}" ]]; then
    TMT_IMAGE="${TMT_CONTAINER_IMAGE}"
fi

# Optional: Allow passing additional podman run options
TMT_PODMAN_OPTIONS="${TMT_PODMAN_OPTIONS:-}"

# Function to run the container
run_in_container() {
    local image="$1"
    local workdir=$(pwd)
    local cmd_args=("${@:2}") # Capture arguments passed to the proxy script

    # Check if podman is available
    if ! command -v podman &> /dev/null; then
        echo "Error: podman is required to run tmt-proxy" >&2
        exit 1
    fi

    # This would be too annoying, only for some sort of debug prints?
    #echo "Running tmt command in container ($image) using podman..." >&2

    # Check if the container image exists, pull if needed
    if ! podman image exists "$image"; then
        echo "Pulling tmt container image ($image)..." >&2
        podman pull "$image"
    fi

    # Construct the podman run command
    local run_command=("podman" "run" "--rm" "-it")

    # Add user namespace configuration to keep host UID/GID
    run_command+=("--userns=keep-id")

    # Add default volume mounts
    run_command+=("-v" "$workdir:$workdir")
    run_command+=("-v" "$HOME/.ssh:/root/.ssh:ro")
    run_command+=("-v" "/etc/tmt:/etc/tmt")
    run_command+=("-v" "$HOME:$HOME")
    run_command+=("-v" "/var/tmp/tmt:/var/tmp/tmt")

    # TODO Is this needed?
    run_command+=("--security-opt" "label=disable")

    # I presume..
    run_command+=("--network" "host")

    # Set working directory
    run_command+=("-w" "$workdir")

    # Add the image name
    run_command+=("$image")

    # Add the command arguments
    run_command+=("${cmd_args[@]}")

    # Execute the command
    exec "${run_command[@]}"
}

# Call the function with the image and all arguments
run_in_container "$TMT_IMAGE" "$@"
