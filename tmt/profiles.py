# from enum import Enum
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Optional, TypeVar

import tmt.container
import tmt.utils
from tmt._compat.pydantic import ValidationError

# from tmt._compat.pydantic import HttpUrl
from tmt.container import Extra, MetadataContainer, metadata_field
from tmt.log import Logger, Topic
from tmt.utils import FieldValueSource, Path, ShellScript
from tmt.utils.templates import render_template

if TYPE_CHECKING:
    from tmt.base import Core, Test

T = TypeVar('T')


KEY_DIFF_TEMPLATE = """
{{ OLD_VALUE | to_yaml | prefix('- ') | style(fg='red') | trim }}
{{ NEW_VALUE | to_yaml | prefix('+ ') | style(fg='green') | trim }}

Field value source changed from {{ OLD_VALUE_SOURCE.value | style(fg='red') }} to {{ NEW_VALUE_SOURCE.value | style(fg='green') }}
"""  # noqa: E501


class Instruction(MetadataContainer, extra=Extra.allow):
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
                VALUE_SOURCE=current_value_source,
            )

            raw_new_value = tmt.utils.yaml_to_python(rendered_new_value)

            new_value = normalize_callback('', raw_new_value, logger)

            setattr(obj, tmt.container.option_to_key(key), new_value)

            return new_value

        for key, template in self.__dict__.items():
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
                logger.fail(f'!!! unhandled type {type(current_value)}')

            assert type(old_value) is type(current_value)

            current_value_exported = export_callback(current_value)

            if current_value_exported != old_value_exported:
                current_value_source = obj._field_value_sources[key] = FieldValueSource.PROFILE

                logger.info(
                    f"Modified '{obj.name}'",
                    render_template(
                        KEY_DIFF_TEMPLATE,
                        OLD_VALUE={key: old_value_exported},
                        NEW_VALUE={key: current_value_exported},
                        OLD_VALUE_SOURCE=old_value_source,
                        NEW_VALUE_SOURCE=current_value_source,
                    ),
                    topic=Topic.PROFILE,
                )


class Profile(MetadataContainer):
    #: Instructions for modifications of tests.
    test_profile: list[Instruction] = metadata_field(default_factory=list[Instruction])

    #: Instructions for modifications of plans.
    # plan_profile: list[Instruction] = metadata_field(default_factory=list[Instruction])

    #: Instructions for modifications of stories.
    # story_profile: list[Instruction] = metadata_field(default_factory=list[Instruction])

    @classmethod
    def load(cls, path: Path, logger: Logger) -> 'Profile':
        try:
            return Profile.from_yaml(tmt.utils.yaml_to_dict(path.read_text()))

        except ValidationError as exc:
            raise tmt.utils.SpecificationError(f"Invalid profile in '{path}'.") from exc

    def _apply(
        self,
        objects: Iterable['Core'],
        instructions: Iterable[Instruction],
        logger: Logger,
    ) -> None:
        """
        Apply profile instructions to a set of objects.

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
        profile_name: Optional[str] = None,
        logger: Logger,
    ) -> None:
        """
        Apply profile to given tests.

        :param tests: tests to modify.
        :param profile_name: if set, record this name in logging.
        :param logger: used for logging.
        """

        # TODO: profile name should be known to this class, maybe set
        # an "origin" field when loading from file (can't do it now, the
        # field is not inherited and I don't know why...)
        if profile_name is not None:
            logger.info(
                f"Apply tmt profile '{profile_name}'.",
                color='green',
                topic=Topic.PROFILE,
            )

        else:
            logger.info(
                "Apply tmt profile.",
                color='green',
                topic=Topic.PROFILE,
            )

        self._apply(tests, self.test_profile, logger.descend())
