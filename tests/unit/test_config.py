import queue
import re
import textwrap
import threading
import unittest
import unittest.mock
from unittest.mock import MagicMock

import fmf
import pytest

import tmt.config
from tmt.utils import Path


@pytest.fixture
def config_path(tmppath: Path, monkeypatch) -> Path:
    config_path = tmppath / 'config'
    config_path.mkdir()
    monkeypatch.setattr(tmt.config, 'effective_config_dir', MagicMock(return_value=config_path))
    return config_path


def test_config(config_path: Path):
    """ Config smoke test """
    run = Path('/var/tmp/tmt/test')
    config1 = tmt.config.Config()
    config1.last_run = run
    config2 = tmt.config.Config()
    assert config2.last_run.resolve() == run.resolve()


def test_last_run_race(tmppath: Path, monkeypatch):
    """ Race in last run symlink shouldn't be fatal """
    config_path = tmppath / 'config'
    config_path.mkdir()
    monkeypatch.setattr(tmt.config, 'effective_config_dir', MagicMock(return_value=config_path))
    mock_logger = unittest.mock.MagicMock()
    monkeypatch.setattr(tmt.utils.log, 'warning', mock_logger)
    config = tmt.config.Config()
    results = queue.Queue()
    threads = []

    def create_last_run(config, counter):
        try:
            last_run_path = tmppath / f"run-{counter}"
            last_run_path.mkdir()
            val = config.last_run = last_run_path
            results.put(val)
        except Exception as err:
            results.put(err)

    total = 20
    for i in range(total):
        threads.append(threading.Thread(target=create_last_run, args=(config, i)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_good = True
    for _ in threads:
        value = results.get()
        if isinstance(value, Exception):
            # Print exception for logging
            print(value)
            all_good = False
    assert all_good
    # Getting into race is not certain, do not assert
    # assert mock_logger.called
    assert config.last_run, "Some run was stored as last run"


def test_link_config_invalid(config_path: Path):
    config_yaml = textwrap.dedent("""
        issue-tracker:
          - type: jiRA
            url: invalid_url
            tmt-web-url: https://
            unknown: value
        additional_key:
          foo: bar
        """).strip()
    fmf.Tree.init(path=config_path)
    (config_path / 'link.fmf').write_text(config_yaml)

    with pytest.raises(tmt.utils.MetadataError) as error:
        _ = tmt.config.Config().link

    cause = str(error.value.__cause__)
    assert '6 validation errors for LinkConfig' in cause
    assert re.search(r'type\s*value is not a valid enumeration member', cause)
    assert re.search(r'url\s*invalid or missing URL scheme', cause)
    assert re.search(r'tmt-web-url\s*URL host invalid', cause)
    assert re.search(r'unknown\s*extra fields not permitted', cause)
    assert re.search(r'token\s*field required', cause)
    assert re.search(r'additional_key\s*extra fields not permitted', cause)


def test_link_config_valid(config_path: Path):
    config_yaml = textwrap.dedent("""
        issue-tracker:
          - type: jira
            url: https://issues.redhat.com
            tmt-web-url: https://tmt-web-url.com
            token: secret
        """).strip()
    fmf.Tree.init(path=config_path)
    (config_path / 'link.fmf').write_text(config_yaml)

    link = tmt.config.Config().link

    assert link.issue_tracker[0].type == 'jira'
    assert link.issue_tracker[0].url == 'https://issues.redhat.com'
    assert link.issue_tracker[0].tmt_web_url == 'https://tmt-web-url.com'
    assert link.issue_tracker[0].token == 'secret'


def test_link_config_missing(config_path: Path):
    fmf.Tree.init(path=config_path)

    assert tmt.config.Config().link is None


def test_link_config_empty(config_path: Path):
    fmf.Tree.init(path=config_path)
    (config_path / 'link.fmf').touch()

    with pytest.raises(tmt.utils.SpecificationError) as error:
        _ = tmt.config.Config().link

    cause = str(error.value.__cause__)
    assert '1 validation error for LinkConfig' in cause
    assert re.search(r'issue-tracker\s*field required', cause)
