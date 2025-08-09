from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Optional, TypeVar

import tmt.container
import tmt.utils
from tmt._compat.pydantic import ValidationError
from tmt.container import PYDANTIC_V1, ConfigDict, MetadataContainer, metadata_field
from tmt.log import Logger, Topic
from tmt.utils import FieldValueSource, Path, ShellScript
from tmt.utils.templates import render_template

if TYPE_CHECKING:
    from tmt.base import Core, Test

T = TypeVar('T')


#: A template showing changes made by an instruction.
KEY_DIFF_TEMPLATE = """
{{ OLD_VALUE | to_yaml | prefix('- ') | style(fg='red') | trim }}
{{ NEW_VALUE | to_yaml | prefix('+ ') | style(fg='green') | trim }}

Field value source changed from {{ OLD_VALUE_SOURCE.value | style(fg='red') }} to {{ NEW_VALUE_SOURCE.value | style(fg='green') }}
"""  # noqa: E501


class Instruction(MetadataContainer):
    """
    A single instruction describing changes to test, plan or story keys.
    """

    if PYDANTIC_V1:

        class Config(MetadataContainer.Config):
            extra = "allow"
    else:
        model_config = ConfigDict(extra="allow")

    def apply(self, obj: 'Core', logger: Logger) -> None:
        """
        Apply the instruction to a given object.

        :param obj: object to modify - a test, plan, or story.
        :param logger: used for logging.
        """

        base_logger = logger

        def set_key(
            key: str,
            template: str,
            current_value_exported: Any,
            current_value_source: FieldValueSource,
            normalize_callback: tmt.container.NormalizeCallback[T],
        ) -> T:
            """
            Update a single key of the object.

            :param key: name of the key to update.
            :param template: template rendering to a new value.
            :param current_value_exported: current value as if exported
                via :py:meth:`Core._export`. Consists of Python built-in
                types only, no custom classes.
            :param current_value_source: origin of the current value.
            :param normalize_callback: will be called with the rendered
                ``template`` to produce new value for the key.
            """

            rendered_new_value = render_template(
                template,
                VALUE=current_value_exported,
                VALUE_SOURCE=current_value_source.value,
            )

            raw_new_value = tmt.utils.yaml_to_python(rendered_new_value)

            new_value = normalize_callback('', raw_new_value, logger)

            setattr(obj, tmt.container.option_to_key(key), new_value)

            return new_value

        for key in self.model_fields_set:
            template = getattr(self, key)
            logger = base_logger.clone()

            _, _, _, _, field_metadata = tmt.container.container_field(obj, key)

            normalize_callback: Optional[tmt.container.NormalizeCallback[Any]] = (
                field_metadata.normalize_callback
            )
            export_callback: Optional[tmt.container.FieldExporter[Any]] = (
                field_metadata.export_callback
            )

            if normalize_callback is None:
                logger.warning(f"key '{key}' lacks normalizer")

                normalize_callback = lambda key_address, value, logger: value  # noqa: E731

            if export_callback is None:
                logger.warning(f"key '{key}' lacks exporter")

                export_callback = lambda value: value  # noqa: E731

            current_value = old_value = getattr(obj, tmt.container.option_to_key(key))
            current_value_exported = old_value_exported = export_callback(current_value)
            current_value_source = old_value_source = obj._field_value_sources[key]

            if isinstance(
                current_value,
                (float, int, bool, str, list, dict, ShellScript, tmt.utils.Environment),
            ):
                current_value = set_key(
                    key,
                    template,
                    current_value_exported,
                    current_value_source,
                    normalize_callback,
                )

            else:
                raise tmt.utils.GeneralError(
                    f"Field '{key}' of type '{type(current_value)}' is not supported by a policy."
                )

            if type(old_value) is not type(current_value):
                raise tmt.utils.GeneralError(
                    f"Type mismatch for field '{key}': expected '{type(old_value)}', "
                    f"got '{type(current_value)}'."
                )

            current_value_exported = export_callback(current_value)

            if current_value_exported != old_value_exported:
                current_value_source = obj._field_value_sources[key] = FieldValueSource.POLICY

                logger.info(
                    f"Modified '{obj.name}'",
                    render_template(
                        KEY_DIFF_TEMPLATE,
                        OLD_VALUE={key: old_value_exported},
                        NEW_VALUE={key: current_value_exported},
                        OLD_VALUE_SOURCE=old_value_source,
                        NEW_VALUE_SOURCE=current_value_source,
                    ),
                    topic=Topic.POLICY,
                )


class Policy(MetadataContainer):
    """
    A tmt run policy.

    A collection of instructions telling tmt how to modify test keys.
    See :ref:`/spec/policy` for more details.
    """

    # The name will be overwritten by the code loading policies
    name: str = 'unknown'

    #: Instructions for modifications of tests.
    test_policy: list[Instruction] = metadata_field(default_factory=list[Instruction])

    #: Instructions for modifications of plans.
    # plan_policy: list[Instruction] = metadata_field(default_factory=list[Instruction])

    #: Instructions for modifications of stories.
    # story_policy: list[Instruction] = metadata_field(default_factory=list[Instruction])

    @classmethod
    def load_by_filepath(cls, *, path: Path, root: Optional[Path] = None) -> 'Policy':
        """
        Load a policy from a given file.

        :param path: a path to the policy file.
        :param root: directory under which policy file must reside.
        """

        if root is not None:
            path = root / path.unrooted()

            if not path.is_relative_to(root):
                raise tmt.utils.SpecificationError(
                    f"Policy '{path}' does not reside under policy root '{root}'."
                )

        try:
            policy = Policy.from_yaml(path.read_text())
            policy.name = str(path)

            return policy

        except FileNotFoundError as exc:
            raise tmt.utils.SpecificationError(f"Policy '{path}' not found.") from exc

        except ValidationError as exc:
            raise tmt.utils.SpecificationError(f"Invalid policy in '{path}'.") from exc

    @classmethod
    def load_by_name(cls, *, name: str, root: Path) -> 'Policy':
        """
        Load a policy from a given directory.

        :param name: suffix-less name of a file under the ``root`` path.
        :param root: directory under which policy file must reside.
        """

        for suffix in ('.yaml', '.yml'):
            filepath = Path(f'{name}{suffix}').unrooted()

            if not (root / filepath).is_file():
                continue

            policy = cls.load_by_filepath(path=filepath, root=root)
            policy.name = name

            return policy

        raise tmt.utils.SpecificationError(f"Policy '{name}' does not point to a file.")

    def _apply(
        self,
        objects: Iterable['Core'],
        instructions: Iterable[Instruction],
        logger: Logger,
    ) -> None:
        """
        Apply policy instructions to a set of objects.

        :param objects: object to modify.
        :param instructions: instructions to apply.
        :param logger: used for logging.
        """

        for obj in objects:
            for instruction in instructions:
                instruction.apply(obj, logger)

    def apply_to_tests(
        self,
        *,
        tests: Iterable['Test'],
        logger: Logger,
    ) -> None:
        """
        Apply policy to given tests.

        :param tests: tests to modify.
        :param policy_name: if set, record this name in logging.
        :param logger: used for logging.
        """

        logger.info(
            f"Apply tmt policy '{self.name}' to tests.",
            color='green',
        )

        self._apply(tests, self.test_policy, logger.descend())
