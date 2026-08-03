from tmt.utils._threading import Lock


def test_sanity() -> None:
    some_data: list[str] = []

    lock: Lock[list[str]] = Lock(some_data)

    assert lock._Lock__lock.locked() is False  # type: ignore[attr-defined]
    assert lock._Lock__value is some_data  # type: ignore[attr-defined]

    with lock as data:
        assert lock._Lock__lock.locked() is True  # type: ignore[attr-defined]
        assert data is some_data

    assert lock._Lock__lock.locked() is False  # type: ignore[attr-defined]
    assert lock._Lock__value is some_data  # type: ignore[attr-defined]
