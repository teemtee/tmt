import pytest

import tmt.base.core
import tmt.libraries
import tmt.utils


def test_basic(root_logger, source_dir, target_dir):
    """
    Test basic scenario for file requirement
    """

    parent = tmt.utils.Common(logger=root_logger, workdir=True)
    tmt.libraries.Library.from_identifier(
        logger=root_logger,
        parent=parent,
        identifier=tmt.base.core.DependencyFile(type='file', pattern=['lib.*']),
        source_location=source_dir,
        target_location=target_dir,
    )
    assert target_dir.exists()
    assert target_dir.is_dir()
    target_content = list(target_dir.iterdir())
    assert target_dir / 'library' in target_content
    assert target_dir / 'lib_folder' in target_content


def test_full_copy(root_logger, source_dir, target_dir):
    """
    Test copying everything from the source directory
    """

    parent = tmt.utils.Common(logger=root_logger, workdir=True)
    tmt.libraries.Library.from_identifier(
        logger=root_logger,
        parent=parent,
        identifier=tmt.base.core.DependencyFile(type='file', pattern=['/']),
        source_location=source_dir,
        target_location=target_dir,
    )
    assert (target_dir / 'tests/bz6/runtests.sh').exists()


def test_nothing_found(root_logger, source_dir, target_dir):
    """
    Test Library error is thrown when no files are found
    """

    parent = tmt.utils.Common(logger=root_logger, workdir=True)
    with pytest.raises(tmt.libraries.LibraryError):
        tmt.libraries.Library.from_identifier(
            logger=root_logger,
            parent=parent,
            identifier=tmt.base.core.DependencyFile(type='file', pattern=['/should/not/exist']),
            source_location=source_dir,
            target_location=target_dir,
        )
