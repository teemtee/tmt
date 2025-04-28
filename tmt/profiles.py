# from enum import Enum
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Optional, TypeVar

import tmt.container
import tmt.utils
from tmt._compat.pydantic import ValidationError

# from tmt._compat.pydantic import HttpUrl
from tmt.container import Extra, MetadataContainer, metadata_field
from tmt.log import Logger, Topic
from tmt.utils import Path, ShellScript
from tmt.utils.templates import render_template

if TYPE_CHECKING:
    from tmt.base import Core, Test

T = TypeVar('T')


class Instruction(MetadataContainer, extra=Extra.allow):
    def apply(self, obj: 'Core', logger: Logger) -> None:
        base_logger = logger

        def set_key(
            key: str,
            template: str,
            current_value: T,
            export_callback: tmt.container.FieldExporter[T],
            normalize_callback: tmt.container.NormalizeCallback[T],
            normalize: bool = False,
        ) -> T:
            rendered_new_value = render_template(template, VALUE=export_callback(current_value))

            raw_new_value = tmt.utils.yaml_to_python(rendered_new_value)

            new_value = (
                normalize_callback('', raw_new_value, logger) if normalize else raw_new_value
            )

            setattr(obj, tmt.container.option_to_key(key), new_value)

            return new_value

        for key, template in self.__dict__.items():
            logger = base_logger.clone()

            logger.verbose(f"Update '{key}' of '{obj}'", topic=Topic.PROFILE)
            logger = logger.descend()

            _, _, _, _, field_metadata = tmt.container.container_field(obj, key)

            normalize_callback: Optional[tmt.container.NormalizeCallback[Any]] = (
                field_metadata.normalize_callback
            )
            export_callback: Optional[tmt.container.FieldExporter[Any]] = (
                field_metadata.export_callback
            )

            if normalize_callback is None:
                logger.fail(f'!!! missing normalizer for {key}')

                normalize_callback = lambda key_address, value, logger: value  # noqa: E731

            if export_callback is None:
                logger.fail(f'!!! missing exporter for {key}')

                export_callback = lambda value: value  # noqa: E731

            current_value = old_value = getattr(obj, tmt.container.option_to_key(key))

            if isinstance(current_value, (float, int, bool, str)):
                current_value = set_key(
                    key, template, current_value, export_callback, normalize_callback
                )

            elif isinstance(current_value, (list, dict, ShellScript, tmt.utils.Environment)):
                current_value = set_key(
                    key,
                    template,
                    # reportUnknownArgumentType,unused-ignore: pyright recognizes `instance()`
                    # call, but cannot tell what would be types of keys and values in lists
                    # and dictionaries. We don't care, therefore silencing this report.
                    current_value,  # type: ignore[reportUnknownArgumentType,unused-ignore]
                    export_callback,
                    normalize_callback,
                    normalize=True,
                )

            else:
                logger.fail(f'!!! unhandled type {type(current_value)}')

            assert type(old_value) is type(current_value)


class Profile(MetadataContainer):
    test_profile: list[Instruction] = metadata_field(default_factory=list[Instruction])
    plan_profile: list[Instruction] = metadata_field(default_factory=list[Instruction])
    story_profile: list[Instruction] = metadata_field(default_factory=list[Instruction])

    @classmethod
    def load(cls, path: Path, logger: Logger) -> 'Profile':
        try:
            return Profile.from_yaml(tmt.utils.yaml_to_dict(path.read_text()))

        except ValidationError as exc:
            raise tmt.utils.SpecificationError(f"Invalid profile in '{path}'.") from exc

    def _apply(
        self, tests: Iterable['Test'], instructions: Iterable[Instruction], logger: Logger
    ) -> None:
        for instruction in instructions:
            for test in tests:
                instruction.apply(test, logger)

    def apply_to_tests(self, tests: Iterable['Test'], logger: Logger) -> None:
        self._apply(tests, self.test_profile, logger)
