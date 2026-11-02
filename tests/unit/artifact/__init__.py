from unittest.mock import patch

MOCK_BUILD_ID_KOJI_BREW = 2829512

MOCK_RPMS_KOJI = [
    {"name": f"pkg{i}", "version": "1.0", "release": "1.fc43", "arch": "x86_64"} for i in range(13)
]

MOCK_RPMS_BREW = [
    {"name": f"pkg{i}", "version": "1.0", "release": "1.el9", "arch": "x86_64"} for i in range(21)
]

MOCK_COPR_RPM_URL = "https://download.copr.fedorainfracloud.org/results/user/project/fedora-rawhide-x86_64/11230530-tmt"
MOCK_RPMS_COPR = [f"{MOCK_COPR_RPM_URL}/pkg{i}-1.0-1.fc41.x86_64" for i in range(14)]


def mock_koji_brew_build_api_responses(mock_call_api, mock_rpms=None):
    """Mock API responses for koji/brew builds."""
    if mock_rpms is None:
        mock_rpms = MOCK_RPMS_KOJI

    def mock_api(method, *args, **kwargs):
        if method == "listBuildRPMs":
            return mock_rpms
        if method == "getBuild":
            return {
                "id": MOCK_BUILD_ID_KOJI_BREW,
                "package_name": "test-package",
                "version": "1.0",
                "release": "1.fc43",
            }
        return None

    mock_call_api.side_effect = mock_api


def mock_task_api_responses(mock_call_api, mock_rpms=None, has_build=True):
    """Mock API responses for koji/brew tasks."""
    if mock_rpms is None:
        mock_rpms = MOCK_RPMS_KOJI

    def mock_api(method, *args, **kwargs):
        if method == "listBuilds":
            return [{"build_id": MOCK_BUILD_ID_KOJI_BREW}] if has_build else []
        if method == "listBuildRPMs":
            return mock_rpms
        if method == "getBuild":
            return {
                "id": MOCK_BUILD_ID_KOJI_BREW,
                "package_name": "test-package",
                "version": "1.0",
                "release": "1.fc43",
            }
        if method == "getTaskDescendents":
            task_id = args[0] if args else kwargs.get('taskID')
            return {str(task_id): None, str(task_id + 1): None}
        if method == "listTaskOutput":
            return ["foo-1.0-1.fc43.x86_64.rpm", "bar-2.0-1.fc43.x86_64.rpm"]
        return None

    mock_call_api.side_effect = mock_api


def mock_call_api_for(provider_class):
    return patch.object(provider_class, "_call_api")
