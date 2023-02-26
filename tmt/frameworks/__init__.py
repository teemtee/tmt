from typing import TYPE_CHECKING, Callable, List, Type

import tmt.log
import tmt.plugins
import tmt.result
import tmt.utils

if TYPE_CHECKING:
    from tmt.base import Test
    from tmt.steps.execute import ExecutePlugin
    from tmt.steps.provision import Guest


TestFrameworkClass = Type['TestFramework']


_FRAMEWORK_PLUGIN_REGISTRY: tmt.plugins.PluginRegistry[TestFrameworkClass] = \
    tmt.plugins.PluginRegistry()


def provides_framework(framework: str) -> Callable[[TestFrameworkClass], TestFrameworkClass]:
    """
    A decorator for registering test frameworks.

    Decorate a test framework plugin class to register a test framework.
    """

    def _provides_framework(framework_cls: TestFrameworkClass) -> TestFrameworkClass:
        _FRAMEWORK_PLUGIN_REGISTRY.register_plugin(
            plugin_id=framework,
            plugin=framework_cls,
            logger=tmt.log.Logger.get_bootstrap_logger())

        return framework_cls

    return _provides_framework


class TestFramework:
    """
    A base class for test framework plugins.

    All methods provide viable default behavior with the exception of
    :py:meth:`extract_results` which must be implemented by the plugin.
    """

    @classmethod
    def get_environment_variables(
            cls,
            parent: 'ExecutePlugin',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> tmt.utils.EnvironmentType:
        """
        Provide additional environment variables for the test.

        :param parent: ``execute`` plugin managing the test.
        :param test: a test that would be executed.
        :param guest: a guest on which the test would run.
        :param logger: to use for logging.
        :returns: environment variables to expose for the test. Variables
            would be added on top of any variables the plugin, test or plan
            might have already collected.
        """

        return {}

    @classmethod
    def get_test_command(
            cls,
            parent: 'ExecutePlugin',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> tmt.utils.ShellScript:
        """
        Provide a test command.

        :param parent: ``execute`` plugin managing the test.
        :param test: a test that would be executed.
        :param guest: a guest on which the test would run.
        :param logger: to use for logging.
        :returns: a command to use to run the test.
        """

        assert test.test is not None  # narrow type

        return test.test

    @classmethod
    def get_pull_options(
            cls,
            parent: 'ExecutePlugin',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> List[str]:
        """
        Provide additional options for pulling test data directory.

        :param parent: ``execute`` plugin managing the test.
        :param test: a test that would be executed.
        :param guest: a guest on which the test would run.
        :param logger: to use for logging.
        :returns: additional options for the ``rsync`` tmt would use to pull
            the test data directory from the guest.
        """

        return []

    @classmethod
    def extract_results(
            cls,
            parent: 'ExecutePlugin',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> List[tmt.result.Result]:
        """
        Extract test results.

        :param parent: ``execute`` plugin managing the test.
        :param test: a test that would be executed.
        :param guest: a guest on which the test would run.
        :param logger: to use for logging.
        :returns: list of results produced by the given test.
        """

        raise NotImplementedError
