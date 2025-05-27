import dataclasses
import inspect
import re
from collections.abc import Iterator
from typing import Any, Callable, Optional, cast

import tmt
import tmt.base
import tmt.container
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.steps.provision
import tmt.utils
from tmt.container import container
from tmt.plugins import PluginRegistry
from tmt.result import PhaseResult
from tmt.steps.provision import Guest
from tmt.utils import Path
from tmt.utils.templates import render_template

FEATURE_PLAYEBOOK_DIRECTORY = tmt.utils.resource_files('steps/prepare/feature')

FeatureClass = type['FeatureBase']
_FEATURE_PLUGIN_REGISTRY: PluginRegistry[FeatureClass] = PluginRegistry('prepare.feature')


#: A pattern for matching module-like keys in Ansible playbooks.
ANSIBLE_MODULE_NAME_PATTERN = re.compile(r'.+\..+\..+')

#: A template for "used modules" note for plugin docstrings.
ANSIBLE_MODULE_NOTE_TEMPLATE = """
.. note::

    This plugin requires the following Ansible modules be installed
    on the runner:

    {% for module in MODULES %}
    * `{{ module }}`__
    {% endfor %}

    {% for module in MODULES %}
        {% set module_components = module.split('.', 2) %}
    __ https://docs.ansible.com/ansible/latest/collections/{{ module_components[0] }}/{{ module_components[1] }}/{{ module_components[2] }}_module.html
    {% endfor %}
"""  # noqa: E501


def _collect_playbook_modules(feature_cls: FeatureClass, logger: tmt.log.Logger) -> set[str]:
    """
    Find all module-like keys in feature's Ansible playbooks.

    Module-like keys are keys in dictionaries that match the pattern of
    ``foo.bar.baz``, as we enforce fully-qualified module names to be
    used.
    """

    # Find module-like keys in a given object, recursively.
    def _collect_from_object(obj: Any) -> Iterator[str]:
        if isinstance(obj, list):
            for item in obj:
                yield from _collect_from_object(item)

        elif isinstance(obj, dict):
            for key, value in obj.items():
                if ANSIBLE_MODULE_NAME_PATTERN.match(key):
                    yield key

                else:
                    yield from _collect_from_object(value)

    # Find module-like keys in playbooks, inspecting one by one.
    def _collect_from_playbooks(playbooks: set[str]) -> Iterator[str]:
        for playbook_filename in playbooks:
            playbook_filepath = feature_cls._find_playbook(playbook_filename, logger)

            if playbook_filepath is None:
                continue

            yield from _collect_from_object(tmt.utils.yaml_to_list(playbook_filepath.read_text()))

    return set(_collect_from_playbooks(feature_cls.PLAYBOOKS))


def _add_modules_to_docstring(feature_cls: FeatureClass, logger: tmt.log.Logger) -> None:
    """
    Add a list of Ansible modules used by feature's playbooks to its docstring.
    """

    if not feature_cls.__doc__:
        return

    modules = _collect_playbook_modules(feature_cls, logger)

    if not modules:
        return

    feature_cls.__doc__ += '\n' + render_template(ANSIBLE_MODULE_NOTE_TEMPLATE, MODULES=modules)


def provides_feature(feature: str) -> Callable[[FeatureClass], FeatureClass]:
    """
    A decorator for registering feature plugins.

    Decorate a feature plugin class to register a feature:

    .. code-block:: python

        @provides_feature('foo')
        class Foo(ToggleableFeature):
            ...

    Decorator also inspects plugins :py:attr:`FeatureBase.PLAYBOOKS`,
    gathers all Ansible modules from listed playbooks, and adds a note
    to plugin's docstring reminding user about their necessity on the
    runner.
    """

    def _provides_feature(feature_cls: FeatureClass) -> FeatureClass:
        logger = tmt.log.Logger.get_bootstrap_logger()

        feature_cls.FEATURE_NAME = feature

        _FEATURE_PLUGIN_REGISTRY.register_plugin(
            plugin_id=feature,
            plugin=feature_cls,
            logger=logger,
        )

        if feature_cls.PLAYBOOKS:
            _add_modules_to_docstring(feature_cls, logger)

        return feature_cls

    return _provides_feature


def find_plugin(name: str) -> 'FeatureClass':
    """
    Find a plugin by its name.

    :raises GeneralError: when the plugin does not exist.
    """

    plugin = _FEATURE_PLUGIN_REGISTRY.get_plugin(name)

    if plugin is None:
        raise tmt.utils.GeneralError(
            f"Feature plugin '{name}' was not found in the feature registry."
        )

    return plugin


@container
class PrepareFeatureData(tmt.steps.prepare.PrepareStepData):
    # PrepareFeatureData alone is **not** usable for unserialization.
    # We need to provide the actual, composed class.
    @classmethod
    def unserialize_class(cls) -> Any:
        return PrepareFeature.get_data_class()


class FeatureBase(tmt.utils.Common):
    """Base class for ``feature`` plugins"""

    FEATURE_NAME: str
    PLAYBOOKS: set[str] = set()

    #: Plugin's data class listing keys this feature plugin accepts.
    #: It is eventually composed together with other feature plugins
    #: into a single class, :py:class:`PrepareFeatureData`.
    _data_class: type[PrepareFeatureData] = PrepareFeatureData

    @classmethod
    def get_data_class(cls) -> type[PrepareFeatureData]:
        """
        Return step data class for this plugin.

        By default, :py:attr:`_data_class` is returned, but plugin may
        override this method to provide different class.
        """

        return cls._data_class

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def _find_playbook(cls, filename: str, logger: tmt.log.Logger) -> Optional[Path]:
        filepath = FEATURE_PLAYEBOOK_DIRECTORY / filename
        if filepath.exists():
            return filepath

        filepath = Path(inspect.getfile(cls)).parent / filename
        if filepath.exists():
            return filepath

        logger.warning(f"Cannot find any suitable playbook for '{filename}'.", 0)
        return None

    @classmethod
    def _run_playbook(
        cls,
        op: str,
        playbook_filename: str,
        guest: Guest,
        logger: tmt.log.Logger,
    ) -> None:
        playbook_path = cls._find_playbook(playbook_filename, logger)
        if not playbook_path:
            raise tmt.utils.GeneralError(
                f"{op.capitalize()} {cls.FEATURE_NAME.upper()} is not supported on this guest."
            )

        logger.info(f'{op.capitalize()} {cls.FEATURE_NAME.upper()}')
        guest.ansible(playbook_path)


class ToggleableFeature(FeatureBase):
    """Base class for ``feature`` plugins that enable/disable a feature"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        raise NotImplementedError

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        raise NotImplementedError


class Feature(FeatureBase):
    """Base class for ``feature`` plugins that enable a feature"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def enable(cls, guest: Guest, value: str, logger: tmt.log.Logger) -> None:
        raise NotImplementedError


@tmt.steps.provides_method('feature')
class PrepareFeature(tmt.steps.prepare.PreparePlugin[PrepareFeatureData]):
    """
    Easily enable and disable common features

    The ``feature`` plugin provides a comfortable way to enable
    and disable some commonly used functionality such as enabling
    and disabling the ``epel`` repository or the ``fips`` mode.

    .. note::

       The plugin requires a working Ansible to be available on the
       test runner.

    .. warning::

       The plugin may be a subject of various limitations, imposed by
       the fact it uses Ansible to implement some of the features:

       * Ansible 2.17+ no longer supports Python 3.6 and older. Guests
         where Python 3.7+ is not available cannot be prepared with the
         ``feature`` plugin. This has been observed when Fedora Rawhide
         runner is used with CentOS 7 or CentOS Stream 8 guests. Possible
         workarounds: downgrade Ansible tmt uses, or install Python 3.7+
         before using ``feature`` plugin from an alternative repository
         or local build.

    .. code-block:: yaml

        prepare:
            how: feature
            epel: disabled
            crb: enabled
            fips: enabled
            ...

    .. code-block:: shell

        prepare --how feature --epel disabled --crb enabled --fips enabled ...

    .. note::

       Features available via this plugin are implemented and shipped as
       plugins too. The list of available features and configuration keys
       will depend on which plugins you have installed.
    """

    _data_class = PrepareFeatureData

    @classmethod
    def get_data_class(cls) -> type[PrepareFeatureData]:
        """
        Return step data class for this plugin.

        ``prepare/feature`` builds the class in a dynamic way: class'
        fields are defined by discovered feature plugins. Plugins define
        their own data classes, these are collected, their fields
        extracted and merged together with the base data class fields
        (``name``, ``order``, ...) into the final data class of
        ``prepare/feature`` plugin.
        """

        # If this class' data class is not `PrepareFeatureData` anymore,
        # it means this method already constructed the dynamic class.
        if cls._data_class == PrepareFeatureData:
            # Collect fields in the base class, we must filter them out
            # from classes returned by plugins. These fields will be
            # provided by the base class, and repeating them would raise
            # an exception.
            baseclass_fields = list(tmt.container.container_fields(PrepareFeatureData))
            baseclass_field_names = [field.name for field in baseclass_fields]

            component_fields = [
                field
                for plugin in _FEATURE_PLUGIN_REGISTRY.iter_plugins()
                for field in tmt.container.container_fields(plugin.get_data_class())
                if field.name not in baseclass_field_names
            ]

            cls._data_class = cast(
                type[PrepareFeatureData],
                dataclasses.make_dataclass(
                    'PrepareFeatureData',
                    [(field.name, field.type, field) for field in component_fields],
                    bases=(PrepareFeatureData,),
                ),
            )

            # Fix possibly misleading info: it was observed on CentOS
            # Stream 9 where Python & Pydantic set `__module__` to be
            # `types`, resulting in impossible unserialization.
            # `make_dataclass()` offers `module` parameter, but only
            # in newer Python versions.
            cls._data_class.__module__ = cls.__module__
            cls._data_class.__name__ = 'PrepareFeatureData'

        return cls._data_class

    def go(
        self,
        *,
        guest: 'Guest',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[PhaseResult]:
        """
        Prepare the guests
        """

        results = super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.opt('dry'):
            return []

        for plugin_id in _FEATURE_PLUGIN_REGISTRY.iter_plugin_ids():
            plugin_class = find_plugin(plugin_id)

            value = cast(Optional[str], getattr(self.data, plugin_class.FEATURE_NAME, None))
            if value is None:
                continue

            if issubclass(plugin_class, ToggleableFeature):
                value = value.lower()

                if value == 'enabled':
                    plugin_class.enable(guest, logger)
                elif value == 'disabled':
                    plugin_class.disable(guest, logger)
                else:
                    raise tmt.utils.GeneralError(f"Unknown plugin setting '{value}'.")

            elif issubclass(plugin_class, Feature):
                plugin_class.enable(guest, value, logger)

            else:
                raise tmt.utils.GeneralError(f"Unknown plugin implementation '{plugin_class}'.")

        return results

    def essential_requires(self) -> list[tmt.base.Dependency]:
        """
        Collect all essential requirements of the plugin.

        Essential requirements of a plugin are necessary for the plugin to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return tmt.steps.provision.essential_ansible_requires()
