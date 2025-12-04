from unittest.mock import MagicMock, patch

import pytest

from tmt.steps.prepare.artifact.providers.copr_build import CoprBuildArtifactProvider

MOCK_BUILD_ID_KOJI_BREW = 2829512
MOCK_BUILD_ID_COPR = 9820798

MOCK_RPMS_KOJI = [
    {"name": f"pkg{i}", "version": "1.0", "release": "1.fc43", "arch": "x86_64"} for i in range(13)
]

MOCK_RPMS_BREW = [
    {"name": f"pkg{i}", "version": "1.0", "release": "1.el9", "arch": "x86_64"} for i in range(21)
]

MOCK_RPMS_COPR = {
    "fedora-41-x86_64": {
        "packages": [
            {
                "name": f"pkg{i}",
                "version": "1.0",
                "release": "1.fc41",
                "arch": "x86_64",
            }
            for i in range(14)
        ]
    }
}


def mock_koji_brew_build_api_responses(mock_call_api, mock_rpms=None):
    """Mock API responses for koji/brew builds."""
    if mock_rpms is None:
        mock_rpms = MOCK_RPMS_KOJI

    def mock_api(method, *args, **kwargs):
        if method == "listBuildRPMs":
            return mock_rpms
        if method == "getBuild":
            return {"id": MOCK_BUILD_ID_KOJI_BREW}
        return None

    mock_call_api.side_effect = mock_api


def mock_copr_build_api_responses(mock_session, mock_rpms=None):
    if mock_rpms is None:
        mock_rpms = MOCK_RPMS_COPR

    mock_build_proxy = MagicMock()
    mock_build_proxy.get_built_packages.return_value = mock_rpms
    mock_build_proxy.get.return_value = {
        "id": MOCK_BUILD_ID_COPR,
        "source_package": {"name": "tmt"},
    }

    mock_build_chroot_proxy = MagicMock()
    mock_build_chroot_proxy.get.return_value = MagicMock(
        result_url="http://copr.example.com/build/"
    )

    mock_session.build_proxy = mock_build_proxy
    mock_session.build_chroot_proxy = mock_build_chroot_proxy
    return mock_session


def mock_build_api_responses(provider_class, mock_call_api, mock_rpms=None):
    if provider_class == CoprBuildArtifactProvider:
        return mock_copr_build_api_responses(mock_call_api)
    return mock_koji_brew_build_api_responses(mock_call_api, mock_rpms)


def mock_task_api_responses(mock_call_api, mock_rpms=None, has_build=True):
    """Mock API responses for koji/brew tasks."""
    if mock_rpms is None:
        mock_rpms = MOCK_RPMS_KOJI

    def mock_api(method, *args, **kwargs):
        if method == "listBuilds":
            return [{"build_id": MOCK_BUILD_ID_KOJI_BREW}] if has_build else []
        if method == "listBuildRPMs":
            return mock_rpms
        if method == "getTaskDescendents":
            task_id = args[0] if args else kwargs.get('taskID')
            return {str(task_id): None, str(task_id + 1): None}
        if method == "listTaskOutput":
            return ["foo.rpm", "bar.rpm"]
        return None

    mock_call_api.side_effect = mock_api


def mock_call_api_for(provider_class):
    return patch.object(provider_class, "_call_api")
