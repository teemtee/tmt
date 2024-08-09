import shutil
from unittest.mock import MagicMock

import pytest

import tmt
import tmt.base
import tmt.libraries.beakerlib
import tmt.utils.git
from tmt.utils import Path


@pytest.mark.web()
def test_basic(root_logger):
    """ Fetch a beakerlib library with/without providing a parent """
    parent = tmt.utils.Common(logger=root_logger, workdir=True)
    library_with_parent = tmt.libraries.library_factory(
        logger=root_logger,
        identifier=tmt.base.DependencySimple('library(openssl/certgen)'),
        parent=parent)
    library_without_parent = tmt.libraries.library_factory(
        logger=root_logger,
        identifier=tmt.base.DependencySimple('library(openssl/certgen)'))

    for library in [library_with_parent, library_without_parent]:
        assert library.format == 'rpm'
        assert library.repo == Path('openssl')
        assert library.url == 'https://github.com/beakerlib/openssl'
        assert library.ref == 'master'  # The default branch is master
        assert library.dest.resolve() \
            == Path.cwd().joinpath(tmt.libraries.beakerlib.DEFAULT_DESTINATION).resolve()
        shutil.rmtree(library.parent.workdir)


@pytest.mark.web()
@pytest.mark.parametrize(
    ('url', 'name', 'default_branch'), [
        ('https://github.com/beakerlib/httpd', '/http', 'master'),
        ('https://github.com/beakerlib/example', '/file', 'main')
        ])
def test_require_from_fmf(url, name, default_branch, root_logger):
    """ Fetch beakerlib library referenced by fmf identifier """
    library = tmt.libraries.library_factory(
        logger=root_logger,
        identifier=tmt.base.DependencyFmfId(
            url=url,
            name=name))
    assert library.format == 'fmf'
    assert library.ref == default_branch
    assert library.url == url
    assert library.dest.resolve() \
        == Path.cwd().joinpath(tmt.libraries.beakerlib.DEFAULT_DESTINATION).resolve()
    assert library.repo == Path(url.split('/')[-1])
    assert library.name == name
    shutil.rmtree(library.parent.workdir)


@pytest.mark.web()
def test_invalid_url_conflict(root_logger):
    """ Saner check if url mismatched for translated library """
    parent = tmt.utils.Common(logger=root_logger, workdir=True)
    # Fetch to cache 'tmt' repo
    tmt.libraries.library_factory(
        logger=root_logger,
        identifier=tmt.base.DependencyFmfId(
            url='https://github.com/teemtee/tmt',
            name='/',
            path=Path('/tests/libraries/local/data')),
        parent=parent)
    # Library 'tmt' repo is already fetched from different git,
    # however upstream (gh.com/beakerlib/tmt) repo does not exist,
    # so there can't be "already fetched" error
    with pytest.raises(tmt.libraries.LibraryError):
        tmt.libraries.library_factory(
            logger=root_logger, identifier='library(tmt/foo)', parent=parent)
    shutil.rmtree(parent.workdir)


@pytest.mark.web()
def test_dependencies(root_logger):
    """ Check requires for possible libraries """
    parent = tmt.utils.Common(logger=root_logger, workdir=True)
    requires, recommends, libraries = tmt.libraries.dependencies(
        original_require=[
            tmt.base.DependencySimple('library(httpd/http)'), tmt.base.DependencySimple('wget')],
        original_recommend=[tmt.base.DependencySimple('forest')],
        parent=parent,
        logger=root_logger)
    # Check for correct requires and recommends
    for require in ['httpd', 'lsof', 'mod_ssl']:
        assert require in requires
        assert require in libraries[0].require
    assert 'openssl' in libraries[2].require
    assert 'forest' in recommends
    assert 'wget' in requires
    # Library require should be in httpd requires but not in the final result
    assert 'library(openssl/certgen)' in libraries[0].require
    assert 'library(openssl/certgen)' not in requires
    # Check library attributes for sane values
    assert libraries[0].repo == Path('httpd')
    assert libraries[0].name == '/http'
    assert libraries[0].url == 'https://github.com/beakerlib/httpd'
    assert libraries[0].ref == 'master'  # The default branch is master
    assert libraries[0].dest.resolve() == Path.cwd().joinpath(
        tmt.libraries.beakerlib.DEFAULT_DESTINATION).resolve()
    assert libraries[1].repo == Path('openssl')
    assert libraries[1].name == '/certgen'
    shutil.rmtree(parent.workdir)


@pytest.mark.web()
def test_mark_nonexistent_url(root_logger, monkeypatch):
    """ Check url existence just one time """
    parent = tmt.utils.Common(logger=root_logger, workdir=True)
    identifier = tmt.base.DependencyFmfId(
        url='https://github.com/beakerlib/THISDOESNTEXIST',
        name='/',
        )
    with pytest.raises(tmt.utils.GeneralError):
        tmt.libraries.beakerlib.BeakerLib(
            logger=root_logger,
            identifier=identifier,
            parent=parent).fetch()
    # Second time there shouldn't be an attempt to clone...
    monkeypatch.setattr("tmt.utils.git.git_clone", MagicMock(
        side_effect=RuntimeError('Should not be called')))
    with pytest.raises(tmt.utils.GeneralError):
        tmt.libraries.beakerlib.BeakerLib(
            logger=root_logger,
            identifier=identifier,
            parent=parent).fetch()
    shutil.rmtree(parent.workdir)
