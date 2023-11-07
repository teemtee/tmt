import pytest

import tmt
import tmt.log
from tmt.utils import Path

logger = tmt.log.Logger.create()

tree = tmt.Tree(logger=logger, path='data')


def test_root():
    root = tree.tests(names=['/root'])[0]
    assert root.summary == 'Test in the root directory'
    assert root.path.resolve() == Path('/')


def test_simple():
    simple = tree.tests(names=['/simple'])[0]
    assert simple.summary == 'Simple test in a separate directory'
    assert simple.path.resolve() == Path('/simple')


def test_virtual():
    for virtual in tree.tests(names=['/virtual']):
        assert 'Virtual test' in virtual.summary
        assert virtual.path.resolve() == Path('/virtual')


def test_weird():
    with pytest.raises(tmt.utils.NormalizationError):
        assert tree.tests(names=['/weird'])[0] is not None
