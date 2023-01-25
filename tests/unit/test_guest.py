from tmt.log import Logger
from tmt.steps.provision import Guest, GuestData


def test_full_name(root_logger: Logger) -> None:
    assert Guest(
        logger=root_logger,
        name='foo',
        data=GuestData(guest='bar')).full_name == 'foo'

    assert Guest(
        logger=root_logger,
        name='foo',
        data=GuestData(guest='bar', role='client')).full_name == 'foo (client)'
