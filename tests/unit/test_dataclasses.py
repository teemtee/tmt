import dataclasses
from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

import tmt.log
import tmt.utils
from tmt.utils import (
    SerializableContainer,
    dataclass_field_by_name,
    dataclass_field_metadata,
    dataclass_normalize_field,
    field,
    )


def test_sanity():
    pass


def test_field_normalize_callback(root_logger: tmt.log.Logger) -> None:
    def _normalize_foo(key_address: str, raw_value: Any, logger: tmt.log.Logger) -> int:
        if raw_value is None:
            return None

        try:
            return int(raw_value)

        except ValueError as exc:
            raise tmt.utils.NormalizationError(key_address, raw_value, 'unset or an integer') \
                from exc

    @dataclasses.dataclass
    class DummyContainer(SerializableContainer):
        foo: Optional[int] = field(
            default=1,
            normalize=_normalize_foo
            )

    # Initialize a data package
    data = DummyContainer()
    assert data.foo == 1

    dataclass_normalize_field(data, ':foo', 'foo', None, root_logger)
    assert data.foo is None

    dataclass_normalize_field(data, ':foo', 'foo', 2, root_logger)
    assert data.foo == 2

    dataclass_normalize_field(data, ':foo', 'foo', '3', root_logger)
    assert data.foo == 3

    with pytest.raises(
            tmt.utils.SpecificationError,
            match=r"Field ':foo' must be unset or an integer, 'str' found."):
        dataclass_normalize_field(data, ':foo', 'foo', 'will crash', root_logger)

    assert data.foo == 3


def test_field_normalize_special_method(root_logger: tmt.log.Logger) -> None:
    def normalize_foo(cls, key_address: str, raw_value: Any, logger: tmt.log.Logger) -> int:
        if raw_value is None:
            return None

        try:
            return int(raw_value)

        except ValueError as exc:
            raise tmt.utils.NormalizationError(key_address, raw_value, 'unset or an integer') \
                from exc

    @dataclasses.dataclass
    class DummyContainer(SerializableContainer):
        foo: Optional[int] = field(
            default=1
            )

        _normalize_foo = normalize_foo

    # Initialize a data package
    data = DummyContainer()
    assert data.foo == 1

    dataclass_normalize_field(data, ':foo', 'foo', None, root_logger)
    assert data.foo is None

    dataclass_normalize_field(data, ':foo', 'foo', 2, root_logger)
    assert data.foo == 2

    dataclass_normalize_field(data, ':foo', 'foo', '3', root_logger)
    assert data.foo == 3

    with pytest.raises(
            tmt.utils.SpecificationError,
            match=r"Field ':foo' must be unset or an integer, 'str' found."):
        dataclass_normalize_field(data, ':foo', 'foo', 'will crash', root_logger)

    assert data.foo == 3


def test_normalize_callback_preferred(root_logger: tmt.log.Logger) -> None:
    @dataclasses.dataclass
    class DummyContainer(SerializableContainer):
        foo: Optional[int] = field(default=1)

        _normalize_foo = MagicMock()

    data = DummyContainer()
    foo_metadata = dataclass_field_metadata(dataclass_field_by_name(data, 'foo'))

    foo_metadata.normalize_callback = MagicMock()

    dataclass_normalize_field(data, ':foo', 'foo', 'will crash', root_logger)

    foo_metadata.normalize_callback.assert_called_once_with(':foo', 'will crash', root_logger)
    data._normalize_foo.assert_not_called()


def test_field_custom_serialize():
    @dataclasses.dataclass
    class DummyContainer(SerializableContainer):
        foo: List[str] = field(
            default_factory=list,
            serialize=lambda foo: ['serialized-into'],
            unserialize=lambda serialized_foo: ['unserialized-from']
            )
        bar: str = field(default='should-never-change')

    # Initialize a data package
    data = DummyContainer()
    assert data.foo == []

    # When serialized, custom callback should override whatever was assigned to package keys
    serialized = data.to_serialized()
    assert serialized['foo'] == ['serialized-into']
    assert serialized['bar'] == 'should-never-change'

    # Yep, the custom callback should be stronger than the original value.
    data.foo = ['baz']
    serialized = data.to_serialized()
    assert serialized['foo'] == ['serialized-into']
    assert serialized['bar'] == 'should-never-change'

    # And the custom unserialize callback should also take an effect: value stored in
    # the package would be serializd into a different one by the custom serialize callback,
    # but then, when unserializing, the custom unserialize callback should lead to the key
    # having yet another value.
    data = DummyContainer()
    serialized = data.to_serialized()
    # We cannot compare `data` and output of `from_serialized()` because the unserialization
    # loads different value into the `foo` key, on purpose.
    data = DummyContainer.from_serialized(serialized)
    assert data.foo == ['unserialized-from']
    assert serialized['bar'] == 'should-never-change'
