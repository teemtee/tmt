import argparse
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

import tmt.log
from tmt._compat.pathlib import Path
from tmt.utils import Command, CommandOutput, Common, RunError

logger = tmt.log.Logger.create(verbose=1, debug=0, quiet=False)
common = Common(logger=logger)

# Base directory where Containerfiles are located
CONTAINERS_DIR = Path("containers")
# Project root directory (context for podman build)
PROJECT_ROOT = Path.cwd()  # Ensure it's an absolute path for consistency

# Prefixes for image names
TMT_DISTRO_IMAGE_NAME_PREFIX = "tmt/container"
TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX = "tmt/container/test"

# Definitions for the main "distro" tmt images
# Each key should be unique.
DISTRO_IMAGES_CONFIG: dict[str, dict[str, Any]] = {
    "tmt_latest": {
        "name_suffix": "tmt:latest",  # Resulting image: tmt/container/tmt:latest
        "containerfile": "Containerfile.mini",  # Relative to CONTAINERS_DIR
        "squash": True,  # Specific build option for this image
    },
    "tmt_all_latest": {
        "name_suffix": "tmt-all:latest",  # Resulting image: tmt/container/tmt-all:latest
        "containerfile": "Containerfile.full",  # Relative to CONTAINERS_DIR
        "squash": True,
    },
}

# Definitions for the "test" tmt images
# Each key should be unique.
TEST_IMAGES_CONFIG: dict[str, dict[str, Any]] = {
    # Alpine
    "alpine_latest": {"name_suffix": "alpine:latest", "containerfile": "alpine/Containerfile"},
    "alpine_upstream_latest": {
        "name_suffix": "alpine/upstream:latest",
        "containerfile": "alpine/Containerfile.upstream",
    },
    # CentOS 7
    "centos7_latest": {
        "name_suffix": "centos/7:latest",
        "containerfile": "centos/7/Containerfile",
    },
    "centos7_upstream_latest": {
        "name_suffix": "centos/7/upstream:latest",
        "containerfile": "centos/7/Containerfile.upstream",
    },
    # CentOS Stream 9
    "centos_stream9_latest": {
        "name_suffix": "centos/stream9:latest",
        "containerfile": "centos/stream9/Containerfile",
    },
    "centos_stream9_upstream_latest": {
        "name_suffix": "centos/stream9/upstream:latest",
        "containerfile": "centos/stream9/Containerfile.upstream",
    },
    # CentOS Stream 10
    "centos_stream10_latest": {
        "name_suffix": "centos/stream10:latest",
        "containerfile": "centos/stream10/Containerfile",
    },
    "centos_stream10_upstream_latest": {
        "name_suffix": "centos/stream10/upstream:latest",
        "containerfile": "centos/stream10/Containerfile.upstream",
    },
    # Fedora CoreOS
    "fedora_coreos_stable": {
        "name_suffix": "fedora/coreos:stable",
        "containerfile": "fedora/coreos/Containerfile",
    },
    "fedora_coreos_ostree_stable": {
        "name_suffix": "fedora/coreos/ostree:stable",
        "containerfile": "fedora/coreos/ostree/Containerfile",
    },
    # Fedora Latest (adjust version number as 'latest' changes)
    "fedora_latest": {
        "name_suffix": "fedora/latest:latest",
        "containerfile": "fedora/latest/Containerfile",
    },
    "fedora_latest_upstream": {
        "name_suffix": "fedora/latest/upstream:latest",
        "containerfile": "fedora/latest/Containerfile.upstream",
    },
    "fedora_latest_unprivileged": {
        "name_suffix": "fedora/latest/unprivileged:latest",
        "containerfile": "fedora/latest/Containerfile.unprivileged",
    },
    # Fedora Rawhide
    "fedora_rawhide_latest": {
        "name_suffix": "fedora/rawhide:latest",
        "containerfile": "fedora/rawhide/Containerfile",
    },
    "fedora_rawhide_upstream_latest": {
        "name_suffix": "fedora/rawhide/upstream:latest",
        "containerfile": "fedora/rawhide/Containerfile.upstream",
    },
    "fedora_rawhide_unprivileged_latest": {
        "name_suffix": "fedora/rawhide/unprivileged:latest",
        "containerfile": "fedora/rawhide/Containerfile.unprivileged",
    },
    # Fedora 41 (Example, adjust as needed)
    "fedora_41_latest": {
        "name_suffix": "fedora/41:latest",
        "containerfile": "fedora/41/Containerfile",
    },
    "fedora_41_upstream_latest": {
        "name_suffix": "fedora/41/upstream:latest",
        "containerfile": "fedora/41/Containerfile.upstream",
    },
    "fedora_41_unprivileged_latest": {
        "name_suffix": "fedora/41/unprivileged:latest",
        "containerfile": "fedora/41/Containerfile.unprivileged",
    },
    # Fedora 40 (Example, adjust as needed)
    "fedora_40_latest": {
        "name_suffix": "fedora/40:latest",
        "containerfile": "fedora/40/Containerfile",
    },
    "fedora_40_upstream_latest": {
        "name_suffix": "fedora/40/upstream:latest",
        "containerfile": "fedora/40/Containerfile.upstream",
    },
    "fedora_40_unprivileged_latest": {
        "name_suffix": "fedora/40/unprivileged:latest",
        "containerfile": "fedora/40/Containerfile.unprivileged",
    },
    # UBI
    "ubi8_upstream_latest": {
        "name_suffix": "ubi/8/upstream:latest",
        "containerfile": "ubi/8/Containerfile.upstream",
    },
    # Ubuntu
    "ubuntu_2204_upstream_latest": {
        "name_suffix": "ubuntu/22.04/upstream:latest",
        "containerfile": "ubuntu/22.04/Containerfile.upstream",
    },
    # Debian
    "debian_12_7_upstream_latest": {
        "name_suffix": "debian/12.7/upstream:latest",
        "containerfile": "debian/12.7/Containerfile.upstream",
    },
    # By default, test images are not squashed. If a specific test image needs squashing,
    # add "squash": True to its configuration entry.
}


def _run_command(
    cmd_list: list[str],
    **kwargs: Any,
) -> CommandOutput | None:
    """
    Runs a command with logging using tmt.utils.Common.
    Exits script on RunError if check is True (default for common.run).
    """
    command = Command(*cmd_list)
    try:
        return common.run(command, **kwargs)
    except RunError as e:
        logger.fail(f"Command execution failed: {' '.join(cmd_list)}\n{e}")
        sys.exit(1)  # Original script exits on error.
    except FileNotFoundError:  # Should ideally be caught by Command or RunError
        logger.fail(
            f"Error: Command '{cmd_list[0]}' not found. "
            f"Is podman (or the required tool) installed and in PATH?"
        )
        sys.exit(1)


def _log_message(message: str, level: str = "INFO", file: TextIO = sys.stdout):
    """Prints a timestamped log message to the specified file (stdout or stderr)."""
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}][{level}] {message}", file=file)


# def _get_full_image_name(prefix: str, name_suffix: str) -> str:
#     """Constructs the full image name (e.g., tmt/container/tmt:latest)."""
#     return f"{prefix}/{name_suffix}"


def discover_base_images_from_containerfiles(image_configs: dict[str, dict[str, Any]]) -> set[str]:
    """
    Parses Containerfiles defined in the provided image_configs to find 'FROM' directives
    and extract unique base image names. It avoids adding locally built
    images (matching known prefixes) to the set of base images to be pulled.
    """
    base_images: set[str] = set()
    processed_files: set[Path] = set()  # To avoid reading the same file multiple times

    for config_key, config_details in image_configs.items():
        containerfile_relative_path = config_details["containerfile"]
        containerfile_abs_path = (CONTAINERS_DIR / containerfile_relative_path).resolve()

        if containerfile_abs_path in processed_files:
            continue

        if not containerfile_abs_path.is_file():
            _log_message(
                f"Containerfile for '{config_key}' not found: {containerfile_abs_path}",
                level="WARNING",
                file=sys.stderr,
            )
            continue

        _log_message(f"Scanning for base images in: {containerfile_abs_path} (for '{config_key}')")
        try:
            with open(containerfile_abs_path, encoding="utf-8") as f:
                for _, line in enumerate(f, 1):
                    stripped_line = line.strip()
                    if not stripped_line or stripped_line.startswith("#"):
                        continue

                    parts = stripped_line.split()
                    if not parts or parts[0].upper() != "FROM":
                        continue

                    # Found a FROM line. Now find the image name.
                    image_name_candidate = ""
                    i = 1
                    while i < len(parts):
                        part = parts[i]
                        if part.startswith("--"):
                            if '=' not in part and i + 1 < len(parts):
                                i += 1
                            i += 1
                            continue
                        if part.upper() == "AS":
                            break
                        image_name_candidate = part
                        break
                    if image_name_candidate and (
                        not image_name_candidate.startswith(TMT_DISTRO_IMAGE_NAME_PREFIX)
                        and not image_name_candidate.startswith(
                            TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX
                        )
                        and not image_name_candidate.startswith("localhost/")
                    ):
                        base_images.add(image_name_candidate)
                    # Only process the first FROM line for external base images
                    break
            processed_files.add(containerfile_abs_path)
        except OSError as e:
            _log_message(
                f"Error reading {containerfile_abs_path}: {e}", level="ERROR", file=sys.stderr
            )

    return base_images


def pull_images(image_list: set[str]):
    """Pulls a list of specified images using 'podman pull'."""
    if not image_list:
        logger.info("No unique external base images found to pull.")
        return
    logger.info(
        f"Attempting to pull {len(image_list)} base image(s): {', '.join(sorted(image_list))}"
    )
    for image_name in sorted(image_list):
        logger.info(f"Pulling base image: {image_name}")
        _run_command(["podman", "pull", image_name])
    logger.info("Base image pulling process complete.")


def build_container_image(
    image_key: str,  # The unique key from the config dictionary
    full_image_name: str,  # Complete name for tagging the image (e.g., tmt/container/tmt:latest)
    containerfile_rel_path: str,  # Path to the Containerfile, relative to CONTAINERS_DIR
    squash: bool = False,  # Whether to squash layers, defaults to False
    build_args: dict[str, str] | None = None,  # Optional build arguments
):
    """Builds a single container image using 'podman build'."""
    logger.info(f"Building image '{image_key}': {full_image_name}")
    containerfile_abs_path = (CONTAINERS_DIR / containerfile_rel_path).resolve()
    logger.info(f"  Containerfile: {containerfile_abs_path}")
    logger.info(f"  Squash: {squash}")

    cmd = [
        "podman",
        "build",
        "--tag",
        full_image_name,
        *["--file", str(containerfile_abs_path)],
    ]
    if squash:
        cmd.append("--squash")

    if build_args:
        for arg_key, arg_value in build_args.items():
            cmd.extend(["--build-arg", f"{arg_key}={arg_value}"])

    cmd.append(str(PROJECT_ROOT))  # The build context directory

    _run_command(cmd)
    logger.info(f"Successfully built image '{image_key}': {full_image_name}")


def main():
    """
    Main function to handle command-line argument parsing when the script is run directly.
    This allows the script to be used independently of Poe, for testing or other purposes.
    """
    # Ensure CONTAINERS_DIR exists relative to the script's execution path or project root
    # This check is more about ensuring the script is run from a sensible location (project root)
    if not (PROJECT_ROOT / CONTAINERS_DIR).is_dir():
        logger.fail(
            f"Error: Containers directory '{PROJECT_ROOT / CONTAINERS_DIR}' not found. "
            f"Please run this script from the project root."
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Manage tmt container builds. Can be called by Poe tasks or run directly.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help(sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
