import json
import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests import RunTmt


EXPECTED_PLUGIN_CATEGORIES = (
    textwrap.dedent("""
Export plugins for plan
Export plugins for story
Export plugins for test
Package manager plugins
Plan shapers
prepare/feature plugins
Discover step plugins
Provision step plugins
Prepare step plugins
Execute step plugins
Finish step plugins
Report step plugins
Test check plugins
Test framework plugins
""")
    .strip()
    .split('\n')
)


def test_plugin_ls_human_output(run_tmt: 'RunTmt') -> None:
    """
    Verify human-readable output of ``tmt about plugin ls``.
    """

    result = run_tmt('about', 'plugins', 'ls')

    assert result.exit_code == 0

    assert all(category in result.stdout for category in EXPECTED_PLUGIN_CATEGORIES)


# Hello, traveller. Is this test failing for you? Then you
# probably added new plugin, or changed existing ones, e.g.
# by renaming their registry or moving plugins around. The
# test is a sanity one, making sure tmt discovers all it can,
# updating EXPECTED_PLUGIN_LIST should turn the tide of
# misfortune.
EXPECTED_PLUGIN_LIST = {
    "export.fmfid": ["dict", "json", "template", "yaml"],
    "export.plan": ["dict", "json", "template", "yaml"],
    "export.story": ["dict", "json", "rst", "template", "yaml"],
    "export.test": ["dict", "json", "nitrate", "polarion", "template", "yaml"],
    "package_managers": [
        "apk",
        "apt",
        "bootc",
        "dnf",
        "dnf5",
        "mock-dnf",
        "mock-dnf5",
        "mock-yum",
        "rpm-ostree",
        "yum",
    ],
    "plan_shapers": ["max-tests", "repeat"],
    "prepare.artifact.providers": [
        "brew.build",
        "brew.nvr",
        "brew.task",
        "copr.build",
        "copr.repository",
        "file",
        "koji.build",
        "koji.nvr",
        "koji.task",
        "repository-file",
        "repository-url",
    ],
    "prepare.feature": ["crb", "epel", "fips", "profile"],
    "prepare.install": ["apk", "apt", "bootc", "dnf", "dnf5", "mock", "rpm-ostree", "yum"],
    "step.cleanup": ["tmt"],
    "step.discover": ["fmf", "shell"],
    "step.execute": ["tmt", "upgrade"],
    "step.finish": ["ansible", "shell"],
    "step.prepare": ["ansible", "artifact", "feature", "install", "shell"],
    "step.provision": [
        "artemis",
        "beaker",
        "bootc",
        "connect",
        "container",
        "local",
        "mock",
        "virtual.testcloud",
    ],
    "step.report": ["display", "html", "junit", "polarion", "reportportal"],
    "test.check": [
        "avc",
        "coredump",
        "dmesg",
        "internal/abort",
        "internal/guest",
        "internal/interrupt",
        "internal/invocation",
        "internal/permission",
        "internal/timeout",
        "journal",
        "watchdog",
    ],
    "test.framework": ["beakerlib", "shell"],
}


def test_plugin_ls_expected_plugins(run_tmt: 'RunTmt') -> None:
    """
    Verify ``tmt about plugin ls`` reports all expected modules.
    """

    result = run_tmt('about', 'plugins', 'ls', '--how', 'json')

    assert result.exit_code == 0

    actual_plugins = json.loads(result.stdout)

    # Sort plugins by their name so we can report missing ones without
    # based on stable output. `tmt about plugin ls` is not expected to
    # sort its output, as users can easily pass the output to tools like
    # `jq`.
    actual_plugins = {
        registry_name: sorted(actual_plugins[registry_name]) for registry_name in actual_plugins
    }

    assert actual_plugins == EXPECTED_PLUGIN_LIST
