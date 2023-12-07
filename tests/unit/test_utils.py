import datetime
import logging
import queue
import re
import signal
import textwrap
import threading
import time
import unittest
import unittest.mock
from datetime import timedelta
from typing import Any, Optional
from unittest.mock import MagicMock

import fmf
import pytest

import tmt
import tmt.log
import tmt.plugins
import tmt.steps.discover
import tmt.utils
from tmt.utils import (
    Command,
    Common,
    GeneralError,
    Path,
    ShellScript,
    StructuredField,
    StructuredFieldError,
    WaitingIncompleteError,
    WaitingTimedOutError,
    _CommonBase,
    clonable_git_url,
    duration_to_seconds,
    filter_paths,
    git_add,
    inject_auth_git_url,
    public_git_url,
    validate_git_status,
    wait,
    )

from . import MATCH, assert_log

run = Common(logger=tmt.log.Logger.create(verbose=0, debug=0, quiet=False)).run


@pytest.fixture()
def local_git_repo(tmppath: Path) -> Path:
    origin = tmppath / 'origin'
    origin.mkdir()

    run(Command('git', 'init'), cwd=origin)
    run(
        Command('git', 'config', '--local', 'user.email', 'lzachar@redhat.com'),
        cwd=origin)
    run(
        Command('git', 'config', '--local', 'user.name', 'LZachar'),
        cwd=origin)
    # We need to be able to push, --bare repo is another option here however
    # that would require to add separate fixture for bare repo (unusable for
    # local changes)
    run(
        Command('git', 'config', '--local', 'receive.denyCurrentBranch', 'ignore'),
        cwd=origin)
    origin.joinpath('README').write_text('something to have in the repo')
    run(Command('git', 'add', '-A'), cwd=origin)
    run(
        Command('git', 'commit', '-m', 'initial_commit'),
        cwd=origin)
    return origin


@pytest.fixture()
def origin_and_local_git_repo(local_git_repo: Path) -> tuple[Path, Path]:
    top_dir = local_git_repo.parent
    fork_dir = top_dir / 'fork'
    run(ShellScript(f'git clone {local_git_repo} {fork_dir}').to_shell_command(),
        cwd=top_dir)
    run(ShellScript('git config --local user.email lzachar@redhat.com').to_shell_command(),
        cwd=fork_dir)
    run(ShellScript('git config --local user.name LZachar').to_shell_command(),
        cwd=fork_dir)
    return local_git_repo, fork_dir


@pytest.fixture()
def nested_file(tmppath: Path) -> tuple[Path, Path, Path]:
    top_dir = tmppath / 'top_dir'
    top_dir.mkdir()
    sub_dir = top_dir / 'sub_dir'
    sub_dir.mkdir()
    file = sub_dir / 'file.txt'
    file.touch()
    return top_dir, sub_dir, file


_test_public_git_url_input = [
    (
        'git@github.com:teemtee/tmt.git',
        'https://github.com/teemtee/tmt.git'
        ),
    (
        'ssh://psplicha@pkgs.devel.redhat.com/tests/bash',
        'https://pkgs.devel.redhat.com/git/tests/bash',
        ),
    (
        'git+ssh://psplicha@pkgs.devel.redhat.com/tests/bash',
        'https://pkgs.devel.redhat.com/git/tests/bash',
        ),
    (
        'ssh://pkgs.devel.redhat.com/tests/bash',
        'https://pkgs.devel.redhat.com/git/tests/bash',
        ),
    (
        'git+ssh://psss@pkgs.fedoraproject.org/tests/shell',
        'https://pkgs.fedoraproject.org/tests/shell',
        ),
    (
        'ssh://psss@pkgs.fedoraproject.org/tests/shell',
        'https://pkgs.fedoraproject.org/tests/shell',
        ),
    (
        'ssh://git@pagure.io/fedora-ci/metadata.git',
        'https://pagure.io/fedora-ci/metadata.git',
        ),
    (
        'git@gitlab.com:redhat/rhel/NAMESPACE/COMPONENT.git',
        'https://pkgs.devel.redhat.com/git/NAMESPACE/COMPONENT.git',
        ),
    (
        'https://gitlab.com/redhat/rhel/NAMESPACE/COMPONENT',
        'https://pkgs.devel.redhat.com/git/NAMESPACE/COMPONENT',
        ),
    (
        'https://gitlab.com/redhat/centos-stream/NAMESPACE/COMPONENT.git',
        'https://gitlab.com/redhat/centos-stream/NAMESPACE/COMPONENT.git',
        )
    ]


@pytest.mark.parametrize(
    ('original', 'expected'),
    _test_public_git_url_input,
    ids=[
        f'{original} => {expected}' for original, expected in _test_public_git_url_input
        ])
def test_public_git_url(original: str, expected: str) -> None:
    """ Verify url conversion """

    assert public_git_url(original) == expected


def test_clonable_git_url():
    assert clonable_git_url('git://pkgs.devel.redhat.com/tests/bash') \
        == 'https://pkgs.devel.redhat.com/git/tests/bash'
    assert clonable_git_url('git+ssh://pkgs.devel.redhat.com/tests/bash') \
        == 'git+ssh://pkgs.devel.redhat.com/tests/bash'
    assert clonable_git_url('git://example.com') \
        == 'git://example.com'


def test_inject_auth_git_url(monkeypatch) -> None:
    """ Verify injecting tokens """

    # empty environment
    monkeypatch.setattr('os.environ', {})
    assert inject_auth_git_url('input_text') == 'input_text'

    suffix = '_glab'
    # https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html#clone-repository-using-personal-access-token
    # username can be anything but cannot be an empty string
    monkeypatch.setattr('os.environ', {
        f'{tmt.utils.INJECT_CREDENTIALS_URL_PREFIX}{suffix}': 'https://gitlab.com/namespace/project',
        f'{tmt.utils.INJECT_CREDENTIALS_VALUE_PREFIX}{suffix}': 'foo:abcdefgh',
        f'{tmt.utils.INJECT_CREDENTIALS_VALUE_PREFIX}___': 'FAKE',
        })
    assert inject_auth_git_url('https://gitlab.com/namespace/project') \
        == 'https://foo:abcdefgh@gitlab.com/namespace/project'

    suffix = '_ghub'
    # https://github.blog/2012-09-21-easier-builds-and-deployments-using-git-over-https-and-oauth/
    # just token or username is used (value before @)
    monkeypatch.setattr('os.environ', {
        f'{tmt.utils.INJECT_CREDENTIALS_URL_PREFIX}{suffix}': 'https://github.com/namespace/project',
        f'{tmt.utils.INJECT_CREDENTIALS_VALUE_PREFIX}{suffix}': 'abcdefgh',
        f'{tmt.utils.INJECT_CREDENTIALS_VALUE_PREFIX}___': 'FAKE',
        f'{tmt.utils.INJECT_CREDENTIALS_URL_PREFIX}{suffix}_2': 'https://github.com/other_namespace',
        f'{tmt.utils.INJECT_CREDENTIALS_VALUE_PREFIX}{suffix}_2': 'xyzabcde',
        f'{tmt.utils.INJECT_CREDENTIALS_URL_PREFIX}{suffix}_3': 'https://example.com/broken',
        })
    assert inject_auth_git_url('https://github.com/namespace/project') \
        == 'https://abcdefgh@github.com/namespace/project'
    assert inject_auth_git_url('https://github.com/other_namespace/project') \
        == 'https://xyzabcde@github.com/other_namespace/project'

    with pytest.raises(tmt.utils.GitUrlError):
        inject_auth_git_url('https://example.com/broken/something')


def test_config():
    """ Config smoke test """
    run = Path('/var/tmp/tmt/test')
    config1 = tmt.utils.Config()
    config1.last_run = run
    config2 = tmt.utils.Config()
    assert config2.last_run.resolve() == run.resolve()


def test_last_run_race(tmppath: Path, monkeypatch):
    """ Race in last run symlink should't be fatal """
    config_path = tmppath / 'config'
    config_path.mkdir()
    monkeypatch.setattr(tmt.utils, 'CONFIG_DIR', config_path)
    mock_logger = unittest.mock.MagicMock()
    monkeypatch.setattr(tmt.utils.log, 'warning', mock_logger)
    config = tmt.utils.Config()
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


def test_workdir_env_var(tmppath: Path, monkeypatch, root_logger):
    """ Test TMT_WORKDIR_ROOT environment variable """
    # Cannot use monkeypatch.context() as it is not present for CentOS Stream 8
    monkeypatch.setenv('TMT_WORKDIR_ROOT', str(tmppath))
    common = Common(logger=root_logger)
    common._workdir_init()
    monkeypatch.delenv('TMT_WORKDIR_ROOT')
    assert common.workdir == tmppath / 'run-001'


def test_workdir_root_full(tmppath, monkeypatch, root_logger):
    """ Raise if all ids lower than WORKDIR_MAX are exceeded """
    monkeypatch.setenv('TMT_WORKDIR_ROOT', str(tmppath))
    monkeypatch.setattr(tmt.utils, 'WORKDIR_MAX', 1)
    possible_workdir = tmppath / 'run-001'
    # First call success
    common1 = Common(logger=root_logger)
    common1._workdir_init()
    assert common1.workdir.resolve() == possible_workdir.resolve()
    # Second call has no id to try
    with pytest.raises(GeneralError):
        Common(logger=root_logger)._workdir_init()
    # Removed run-001 should be used again
    common1._workdir_cleanup(common1.workdir)
    assert not possible_workdir.exists()
    common2 = Common(logger=root_logger)
    common2._workdir_init()
    assert common2.workdir.resolve() == possible_workdir.resolve()


def test_workdir_root_race(tmppath, monkeypatch, root_logger):
    """ Avoid race in workdir creation """
    monkeypatch.setattr(tmt.utils, 'WORKDIR_ROOT', tmppath)
    results = queue.Queue()
    threads = []

    def create_workdir():
        try:
            common = Common(logger=root_logger)
            common._workdir_init()
            results.put(common.workdir)
        except Exception as err:
            results.put(err)

    total = 30
    for _ in range(total):
        threads.append(threading.Thread(target=create_workdir))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_good = True
    unique_workdirs = set()
    for _ in threads:
        value = results.get()
        if isinstance(value, Path):
            unique_workdirs.add(value)
        else:
            # None or Exception: Record to the log and fail test
            print(value)
            all_good = False
    assert all_good, "No exception raised"
    assert len(unique_workdirs) == total, "Each workdir is unique"


def test_duration_to_seconds():
    """ Check conversion from sleep time format to seconds """
    assert duration_to_seconds(5) == 5
    assert duration_to_seconds('5') == 5
    assert duration_to_seconds('5s') == 5
    assert duration_to_seconds('5m') == 300
    assert duration_to_seconds('5h') == 18000
    assert duration_to_seconds('5d') == 432000
    assert duration_to_seconds('5d') == 432000
    # `man sleep` says: Given two or more arguments, pause for the amount of time
    # specified by the sum of their values.
    assert duration_to_seconds('1s 2s') == 3
    assert duration_to_seconds('1h 2 3m') == 3600 + 2 + 180
    # Divergence from 'sleep' as that expects space separated arguments
    assert duration_to_seconds('1s2s') == 3
    assert duration_to_seconds('1 m2   m') == 180
    with pytest.raises(tmt.utils.SpecificationError):
        duration_to_seconds('bad')
    with pytest.raises(tmt.utils.SpecificationError):
        duration_to_seconds('1sm')


class TestStructuredField(unittest.TestCase):
    """ Self Test """

    def setUp(self):
        self.header = "This is a header.\n"
        self.footer = "This is a footer.\n"
        self.start = (
            "[structured-field-start]\n"
            "This is StructuredField version 1. "
            "Please, edit with care.\n")
        self.end = "[structured-field-end]\n"
        self.zeroend = "[end]\n"
        self.one = "[one]\n1\n"
        self.two = "[two]\n2\n"
        self.three = "[three]\n3\n"
        self.sections = "\n".join([self.one, self.two, self.three])

    def test_everything(self):
        """ Everything """
        # Version 0
        text0 = "\n".join([
                self.header,
                self.sections, self.zeroend,
                self.footer])
        inited0 = StructuredField(text0, version=0)
        loaded0 = StructuredField()
        loaded0.load(text0, version=0)
        assert inited0.save() == text0
        assert loaded0.save() == text0
        # Version 1
        text1 = "\n".join([
                self.header,
                self.start, self.sections, self.end,
                self.footer])
        inited1 = StructuredField(text1)
        loaded1 = StructuredField()
        loaded1.load(text1)
        assert inited1.save() == text1
        assert loaded1.save() == text1
        # Common checks
        for field in [inited0, loaded0, inited1, loaded1]:
            assert field.header() == self.header
            assert field.footer() == self.footer
            assert field.sections() == ['one', 'two', 'three']
            assert field.get('one') == '1\n'
            assert field.get('two') == '2\n'
            assert field.get('three') == '3\n'

    def test_no_header(self):
        """ No header """
        # Version 0
        text0 = "\n".join([self.sections, self.zeroend, self.footer])
        field0 = StructuredField(text0, version=0)
        assert field0.save() == text0
        # Version 1
        text1 = "\n".join(
                [self.start, self.sections, self.end, self.footer])
        field1 = StructuredField(text1)
        assert field1.save() == text1
        # Common checks
        for field in [field0, field1]:
            assert field.header() == ''
            assert field.footer() == self.footer
            assert field.get('one') == '1\n'
            assert field.get('two') == '2\n'
            assert field.get('three') == '3\n'

    def test_no_footer(self):
        """ No footer """
        # Version 0
        text0 = "\n".join([self.header, self.sections, self.zeroend])
        field0 = StructuredField(text0, version=0)
        assert field0.save() == text0
        # Version 1
        text1 = "\n".join(
                [self.header, self.start, self.sections, self.end])
        field1 = StructuredField(text1)
        assert field1.save() == text1
        # Common checks
        for field in [field0, field1]:
            assert field.header() == self.header
            assert field.footer() == ''
            assert field.get('one') == '1\n'
            assert field.get('two') == '2\n'
            assert field.get('three') == '3\n'

    def test_just_sections(self):
        """ Just sections """
        # Version 0
        text0 = "\n".join([self.sections, self.zeroend])
        field0 = StructuredField(text0, version=0)
        assert field0.save() == text0
        # Version 1
        text1 = "\n".join([self.start, self.sections, self.end])
        field1 = StructuredField(text1)
        assert field1.save() == text1
        # Common checks
        for field in [field0, field1]:
            assert field.header() == ''
            assert field.footer() == ''
            assert field.get('one') == '1\n'
            assert field.get('two') == '2\n'
            assert field.get('three') == '3\n'

    def test_plain_text(self):
        """ Plain text """
        text = "Some plain text.\n"
        field0 = StructuredField(text, version=0)
        field1 = StructuredField(text)
        for field in [field0, field1]:
            assert field.header() == text
            assert field.footer() == ''
            assert field.save() == text
            assert list(field) == []
            assert bool(field) is False

    def test_missing_end_tag(self):
        """ Missing end tag """
        text = "\n".join([self.header, self.sections, self.footer])
        pytest.raises(StructuredFieldError, StructuredField, text, 0)

    def test_broken_field(self):
        """ Broken field"""
        text = "[structured-field-start]"
        pytest.raises(StructuredFieldError, StructuredField, text)

    def test_set_content(self):
        """ Set section content """
        field0 = StructuredField(version=0)
        field1 = StructuredField()
        for field in [field0, field1]:
            field.set("one", "1")
            assert field.get('one') == '1\n'
            field.set("two", "2")
            assert field.get('two') == '2\n'
            field.set("three", "3")
            assert field.get('three') == '3\n'
        assert field0.save() == '\n'.join([self.sections, self.zeroend])
        assert field1.save() == '\n'.join([self.start, self.sections, self.end])

    def test_remove_section(self):
        """ Remove section """
        field0 = StructuredField(
            "\n".join([self.sections, self.zeroend]), version=0)
        field1 = StructuredField(
            "\n".join([self.start, self.sections, self.end]))
        for field in [field0, field1]:
            field.remove("one")
            field.remove("two")
        assert field0.save() == '\n'.join([self.three, self.zeroend])
        assert field1.save() == '\n'.join([self.start, self.three, self.end])

    def test_section_tag_escaping(self):
        """ Section tag escaping """
        field = StructuredField()
        field.set("section", "\n[content]\n")
        reloaded = StructuredField(field.save())
        assert 'section' in reloaded
        assert 'content' not in reloaded
        assert reloaded.get('section') == '\n[content]\n'

    def test_nesting(self):
        """ Nesting """
        # Prepare structure parent -> child -> grandchild
        grandchild = StructuredField()
        grandchild.set('name', "Grand Child\n")
        child = StructuredField()
        child.set('name', "Child Name\n")
        child.set("child", grandchild.save())
        parent = StructuredField()
        parent.set("name", "Parent Name\n")
        parent.set("child", child.save())
        # Reload back and check the names
        parent = StructuredField(parent.save())
        child = StructuredField(parent.get("child"))
        grandchild = StructuredField(child.get("child"))
        assert parent.get('name') == 'Parent Name\n'
        assert child.get('name') == 'Child Name\n'
        assert grandchild.get('name') == 'Grand Child\n'

    def test_section_tags_in_header(self):
        """ Section tags in header """
        field = StructuredField("\n".join(
            ["[something]", self.start, self.one, self.end]))
        assert 'something' not in field
        assert 'one' in field
        assert field.get('one') == '1\n'

    def test_empty_section(self):
        """ Empty section """
        field = StructuredField()
        field.set("section", "")
        reloaded = StructuredField(field.save())
        assert reloaded.get('section') == ''

    def test_section_item_get(self):
        """ Get section item """
        text = "\n".join([self.start, "[section]\nx = 3\n", self.end])
        field = StructuredField(text)
        assert field.get('section', 'x') == '3'

    def test_section_item_set(self):
        """ Set section item """
        text = "\n".join([self.start, "[section]\nx = 3\n", self.end])
        field = StructuredField()
        field.set("section", "3", "x")
        assert field.save() == text

    def test_section_item_remove(self):
        """ Remove section item """
        text = "\n".join(
            [self.start, "[section]\nx = 3\ny = 7\n", self.end])
        field = StructuredField(text)
        field.remove("section", "x")
        assert field.save() == '\n'.join([self.start, '[section]\ny = 7\n', self.end])

    def test_unicode_header(self):
        """ Unicode text in header """
        text = "Už abychom měli unicode jako defaultní kódování!"
        field = StructuredField(text)
        field.set("section", "content")
        assert text in field.save()

    def test_unicode_section_content(self):
        """ Unicode in section content """
        chars = "ěščřžýáíéů"
        text = "\n".join([self.start, "[section]", chars, self.end])
        field = StructuredField(text)
        assert field.get('section').strip() == chars

    def test_unicode_section_name(self):
        """ Unicode in section name """
        chars = "ěščřžýáíéů"
        text = "\n".join([self.start, f"[{chars}]\nx", self.end])
        field = StructuredField(text)
        assert field.get(chars).strip() == 'x'

    def test_header_footer_modify(self):
        """ Modify header & footer """
        original = StructuredField()
        original.set("field", "field-content")
        original.header("header-content\n")
        original.footer("footer-content\n")
        copy = StructuredField(original.save())
        assert copy.header() == 'header-content\n'
        assert copy.footer() == 'footer-content\n'

    def test_trailing_whitespace(self):
        """ Trailing whitespace """
        original = StructuredField()
        original.set("name", "value")
        # Test with both space and tab appended after the section tag
        for char in [" ", "\t"]:
            spaced = re.sub(r"\]\n", f"]{char}\n", original.save())
            copy = StructuredField(spaced)
            assert original.get('name') == copy.get('name')

    def test_carriage_returns(self):
        """ Carriage returns """
        text1 = "\n".join([self.start, self.sections, self.end])
        text2 = re.sub(r"\n", "\r\n", text1)
        field1 = StructuredField(text1)
        field2 = StructuredField(text2)
        assert field1.save() == field2.save()

    def test_multiple_values(self):
        """ Multiple values """
        # Reading multiple values
        section = "[section]\nkey=val1 # comment\nkey = val2\n key = val3 "
        text = "\n".join([self.start, section, self.end])
        field = StructuredField(text, multi=True)
        assert field.get('section', 'key') == ['val1', 'val2', 'val3']
        # Writing multiple values
        values = ['1', '2', '3']
        field = StructuredField(multi=True)
        field.set("section", values, "key")
        assert field.get('section', 'key') == values
        assert 'key = 1\nkey = 2\nkey = 3' in field.save()
        # Remove multiple values
        field.remove("section", "key")
        assert 'key = 1\nkey = 2\nkey = 3' not in field.save()
        pytest.raises(
            StructuredFieldError, field.get, "section", "key")


def test_run_interactive_not_joined(tmppath, root_logger):
    output = ShellScript("echo abc; echo def >2").to_shell_command().run(
        shell=True,
        interactive=True,
        cwd=tmppath,
        env={},
        log=None,
        logger=root_logger)
    assert output.stdout is None
    assert output.stderr is None


def test_run_interactive_joined(tmppath, root_logger):
    output = ShellScript("echo abc; echo def >2").to_shell_command().run(
        shell=True,
        interactive=True,
        cwd=tmppath,
        env={},
        join=True,
        log=None,
        logger=root_logger)
    assert output.stdout is None
    assert output.stderr is None


def test_run_not_joined_stdout(root_logger):
    output = Command("ls", "/").run(
        shell=False,
        cwd=Path.cwd(),
        env={},
        log=None,
        logger=root_logger)
    assert "sbin" in output.stdout


def test_run_not_joined_stderr(root_logger):
    output = ShellScript("ls non_existing || true").to_shell_command().run(
        shell=False,
        cwd=Path.cwd(),
        env={},
        log=None,
        logger=root_logger)
    assert "ls: cannot access" in output.stderr


def test_run_joined(root_logger):
    output = ShellScript("ls non_existing / || true").to_shell_command().run(
        shell=False,
        cwd=Path.cwd(),
        env={},
        log=None,
        join=True,
        logger=root_logger)
    assert "ls: cannot access" in output.stdout
    assert "sbin" in output.stdout


def test_run_big(root_logger):
    script = """
        for NUM in {1..100}; do
            LINE="$LINE n";
        done;
        for NUM in {1..1000}; do
            echo $LINE;
        done
        """

    output = ShellScript(textwrap.dedent(script)).to_shell_command().run(
        shell=False,
        cwd=Path.cwd(),
        env={},
        log=None,
        join=True,
        logger=root_logger)
    assert "n n" in output.stdout
    assert len(output.stdout) == 200000


def test_get_distgit_handler():
    for _wrong_remotes in [[], ["blah"]]:
        with pytest.raises(tmt.utils.GeneralError):
            tmt.utils.get_distgit_handler([])
    # Fedora detection
    returned_object = tmt.utils.get_distgit_handler("""
        remote.origin.url ssh://lzachar@pkgs.fedoraproject.org/rpms/tmt
        remote.lzachar.url ssh://lzachar@pkgs.fedoraproject.org/forks/lzachar/rpms/tmt.git
        """.split('\n'))
    assert isinstance(returned_object, tmt.utils.FedoraDistGit)
    # CentOS detection
    returned_object = tmt.utils.get_distgit_handler("""
        remote.origin.url git+ssh://git@gitlab.com/redhat/centos-stream/rpms/ruby.git
        """.split('\n'))
    assert isinstance(returned_object, tmt.utils.CentOSDistGit)
    # RH Gitlab detection
    returned_object = tmt.utils.get_distgit_handler([
        "remote.origin.url https://<redacted_credentials>@gitlab.com/redhat/rhel/rpms/osbuild.git",
        ])
    assert isinstance(returned_object, tmt.utils.RedHatGitlab)


def test_get_distgit_handler_explicit():
    instance = tmt.utils.get_distgit_handler(usage_name='redhatgitlab')
    assert instance.__class__.__name__ == 'RedHatGitlab'


def test_fedora_dist_git(tmppath):
    # Fake values, production hash is too long
    (tmppath / 'sources').write_text('SHA512 (fn-1.tar.gz) = 09af\n')
    (tmppath / 'tmt.spec').write_text('')
    fedora_sources_obj = tmt.utils.FedoraDistGit()
    assert [("https://src.fedoraproject.org/repo/pkgs/rpms/tmt/fn-1.tar.gz/sha512/09af/fn-1.tar.gz",
            "fn-1.tar.gz")] == fedora_sources_obj.url_and_name(cwd=tmppath)


class TestValidateGitStatus:
    @classmethod
    @pytest.mark.parametrize("use_path",
                             [False, True], ids=["without path", "with path"])
    def test_all_good(
            cls,
            origin_and_local_git_repo: tuple[Path, Path],
            use_path: bool,
            root_logger):
        # No need to modify origin, ignoring it
        mine = origin_and_local_git_repo[1]

        # In local repo:
        # Init tmt and add test
        fmf_root = mine / 'fmf_root' if use_path else mine
        tmt.Tree.init(logger=root_logger, path=fmf_root, template=None, force=None)
        fmf_root.joinpath('main.fmf').write_text('test: echo')
        run(ShellScript(f'git add {fmf_root} {fmf_root / "main.fmf"}').to_shell_command(),
            cwd=mine)
        run(ShellScript('git commit -m add_test').to_shell_command(),
            cwd=mine)
        run(ShellScript('git push').to_shell_command(),
            cwd=mine)
        test = tmt.Tree(logger=root_logger, path=fmf_root).tests()[0]
        validation = validate_git_status(test)
        assert validation == (True, '')

    @classmethod
    def test_no_remote(cls, local_git_repo: Path, root_logger):
        tmt.Tree.init(logger=root_logger, path=local_git_repo, template=None, force=None)
        with open(local_git_repo / 'main.fmf', 'w') as f:
            f.write('test: echo')
        run(ShellScript('git add main.fmf .fmf/version').to_shell_command(),
            cwd=local_git_repo)
        run(ShellScript('git commit -m initial_commit').to_shell_command(),
            cwd=local_git_repo)

        test = tmt.Tree(logger=root_logger, path=local_git_repo).tests()[0]
        val, msg = validate_git_status(test)
        assert not val
        assert "Failed to get remote branch" in msg

    @classmethod
    def test_untracked_fmf_root(cls, local_git_repo: Path, root_logger):
        # local repo is enough since this can't get passed 'is pushed' check
        tmt.Tree.init(logger=root_logger, path=local_git_repo, template=None, force=None)
        # Make sure fmf root is not tracked
        run(
            ShellScript('git rm --cached .fmf/version').to_shell_command(),
            cwd=local_git_repo)
        local_git_repo.joinpath('main.fmf').write_text('test: echo')
        run(
            ShellScript('git add main.fmf').to_shell_command(),
            cwd=local_git_repo)
        run(
            ShellScript('git commit -m missing_fmf_root').to_shell_command(),
            cwd=local_git_repo)

        test = tmt.Tree(logger=root_logger, path=local_git_repo).tests()[0]
        validate = validate_git_status(test)
        assert validate == (False, 'Uncommitted changes in .fmf/version')

    @classmethod
    def test_untracked_sources(cls, local_git_repo: Path, root_logger):
        tmt.Tree.init(logger=root_logger, path=local_git_repo, template=None, force=None)
        local_git_repo.joinpath('main.fmf').write_text('test: echo')
        local_git_repo.joinpath('test.fmf').write_text('tag: []')
        run(ShellScript('git add .fmf/version test.fmf').to_shell_command(),
            cwd=local_git_repo)
        run(
            ShellScript('git commit -m main.fmf').to_shell_command(),
            cwd=local_git_repo)

        test = tmt.Tree(logger=root_logger, path=local_git_repo).tests()[0]
        validate = validate_git_status(test)
        assert validate == (False, 'Uncommitted changes in main.fmf')

    @classmethod
    @pytest.mark.parametrize("use_path",
                             [False, True], ids=["without path", "with path"])
    def test_local_changes(
            cls,
            origin_and_local_git_repo: tuple[Path, Path],
            use_path,
            root_logger):
        origin, mine = origin_and_local_git_repo

        fmf_root = origin / 'fmf_root' if use_path else origin
        tmt.Tree.init(logger=root_logger, path=fmf_root, template=None, force=None)
        fmf_root.joinpath('main.fmf').write_text('test: echo')
        run(ShellScript('git add -A').to_shell_command(), cwd=origin)
        run(ShellScript('git commit -m added_test').to_shell_command(),
            cwd=origin)

        # Pull changes from previous line
        run(ShellScript('git pull').to_shell_command(),
            cwd=mine)

        mine_fmf_root = mine
        if use_path:
            mine_fmf_root = mine / 'fmf_root'
        mine_fmf_root.joinpath('main.fmf').write_text('test: echo ahoy')

        # Change README but since it is not part of metadata we do not check it
        mine.joinpath("README").write_text('changed')

        test = tmt.Tree(logger=root_logger, path=mine_fmf_root).tests()[0]
        validation_result = validate_git_status(test)

        assert validation_result == (
            False, "Uncommitted changes in " + ('fmf_root/' if use_path else '') + "main.fmf")

    @classmethod
    def test_not_pushed(cls, origin_and_local_git_repo: tuple[Path, Path], root_logger):
        # No need for original repo (it is required just to have remote in
        # local clone)
        mine = origin_and_local_git_repo[1]
        fmf_root = mine

        tmt.Tree.init(logger=root_logger, path=fmf_root, template=None, force=None)

        fmf_root.joinpath('main.fmf').write_text('test: echo')
        run(ShellScript('git add main.fmf .fmf/version').to_shell_command(),
            cwd=fmf_root)
        run(ShellScript('git commit -m changes').to_shell_command(),
            cwd=mine)

        test = tmt.Tree(logger=root_logger, path=fmf_root).tests()[0]
        validation_result = validate_git_status(test)

        assert validation_result == (
            False, 'Not pushed changes in .fmf/version main.fmf')


class TestGitAdd:
    @classmethod
    def test_not_in_repository(
            cls,
            nested_file: tuple[Path, Path, Path],
            root_logger):
        top_dir, sub_dir, file = nested_file

        with pytest.raises(GeneralError, match=r"Failed to add path .* to git index."):
            git_add(path=sub_dir, logger=root_logger)

    @classmethod
    def test_in_repository(
            cls,
            nested_file: tuple[Path, Path, Path],
            root_logger):
        top_dir, sub_dir, file = nested_file
        run(ShellScript('git init').to_shell_command(), cwd=top_dir)

        git_add(path=sub_dir, logger=root_logger)

        # Check git status
        result = run(ShellScript('git diff --cached --name-only').to_shell_command(), cwd=top_dir)
        assert result.stdout is not None
        assert result.stdout.strip() == 'sub_dir/file.txt'


#
# tmt.utils.wait() & waiting for things to happen
#
def test_wait_bad_tick(root_logger):
    """
    :py:func:`wait` shall raise an exception when invalid ``tick`` is given.
    """

    with pytest.raises(GeneralError, match='Tick must be a positive integer'):
        wait(Common(logger=root_logger), lambda: False, datetime.timedelta(seconds=1), tick=-1)


def test_wait_deadline_already_passed(root_logger):
    """
    :py:func:`wait` shall not call ``check`` if the given timeout leads to
    already expired deadline.
    """

    ticks = []

    with pytest.raises(WaitingTimedOutError):
        wait(
            Common(logger=root_logger),
            lambda: ticks.append(1),
            datetime.timedelta(seconds=-86400))

    # our callback should not have been called at all
    assert not ticks


def test_wait(root_logger):
    """
    :py:func:`wait` shall call ``check`` multiple times until ``check`` returns
    successfully.
    """

    # Every tick of wait()'s loop, pop one item. Once we get to the end,
    # consider the condition to be fulfilled.
    ticks = list(range(1, 10))

    # Make sure check's return value is propagated correctly, make it unique.
    return_value = unittest.mock.MagicMock()

    def check():
        if not ticks:
            return return_value

        ticks.pop()

        raise WaitingIncompleteError

    # We want to reach end of our list, give enough time budget.
    r = wait(Common(logger=root_logger), check, datetime.timedelta(seconds=3600), tick=0.01)

    assert r is return_value
    assert not ticks


def test_wait_timeout(root_logger):
    """
    :py:func:`wait` shall call ``check`` multiple times until ``check`` running
    out of time.
    """

    check = unittest.mock.MagicMock(
        __name__='mock_check',
        side_effect=WaitingIncompleteError)

    # We want to reach end of time budget before reaching end of the list.
    with pytest.raises(WaitingTimedOutError):
        wait(Common(logger=root_logger), check, datetime.timedelta(seconds=1), tick=0.1)

    # Verify our callback has been called. It's hard to predict how often it
    # should have been called, hopefully 10 times (1 / 0.1), but timing things
    # in test is prone to errors, process may get suspended, delayed, whatever,
    # and we'd end up with 9 calls and a failed test. In any case, it must be
    # 10 or less, because it's not possible to fit 11 calls into 1 second.
    check.assert_called()
    assert len(check.mock_calls) <= 10


def test_wait_success_but_too_late(root_logger):
    """
    :py:func:`wait` shall report failure even when ``check`` succeeds but runs
    out of time.
    """

    def check():
        time.sleep(5)

    with pytest.raises(WaitingTimedOutError):
        wait(Common(logger=root_logger), check, datetime.timedelta(seconds=1))


def test_import_member(root_logger):
    klass = tmt.plugins.import_member(
        module_name='tmt.steps.discover', member_name='Discover', logger=root_logger)

    assert klass is tmt.steps.discover.Discover


def test_import_member_no_such_module(root_logger):
    with pytest.raises(
            tmt.utils.GeneralError,
            match=r"Failed to import module 'tmt\.steps\.nope_does_not_exist'."):
        tmt.plugins.import_member(
            module_name='tmt.steps.nope_does_not_exist',
            member_name='Discover',
            logger=root_logger)


def test_import_member_no_such_class(root_logger):
    with pytest.raises(
            tmt.utils.GeneralError,
            match=r"No such member 'NopeDoesNotExist' in module 'tmt\.steps\.discover'."):
        tmt.plugins.import_member(
            module_name='tmt.steps.discover',
            member_name='NopeDoesNotExist',
            logger=root_logger)


def test_common_base_inheritance(root_logger):
    """ Make sure multiple inheritance of ``Common`` works across all branches """

    class Mixin(_CommonBase):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

            assert kwargs['foo'] == 'bar'

    # Common first, then the mixin class...
    class ClassA(Common, Mixin):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

            assert kwargs['foo'] == 'bar'

    # and also the mixin first, then the common.
    class ClassB(Mixin, Common):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

            assert kwargs['foo'] == 'bar'

    # Make sure both "branches" of inheritance tree are listed,
    # in the correct order.
    assert ClassA.__mro__ == (
        ClassA,
        Common,
        Mixin,
        _CommonBase,
        object
        )

    assert ClassB.__mro__ == (
        ClassB,
        Mixin,
        Common,
        _CommonBase,
        object
        )

    # And that both classes can be instantiated.
    ClassA(logger=root_logger, foo='bar')
    ClassB(logger=root_logger, foo='bar')


@pytest.mark.parametrize(
    ('values', 'expected'),
    [
        ([], []),
        ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]),
        ([1, 2, 1, 2, 3], [1, 2, 3])
        ],
    ids=(
        'empty-list',
        'no-duplicates',
        'duplicates'
        )
    )
def test_uniq(values: list[Any], expected: list[Any]) -> None:
    assert tmt.utils.uniq(values) == expected


@pytest.mark.parametrize(
    ('values', 'expected'),
    [
        ([], []),
        ([1, 2, 3, 4, 5], []),
        ([1, 2, 1, 2, 3, 4, 4], [1, 2, 4])
        ],
    ids=(
        'empty-list',
        'no-duplicates',
        'duplicates'
        )
    )
def test_duplicates(values: list[Any], expected: list[Any]) -> None:
    assert list(tmt.utils.duplicates(values)) == expected


@pytest.mark.parametrize(
    ('lists', 'unique', 'expected'),
    [
        ([], False, []),
        ([[], [], []], False, []),
        ([[], [1, 2, 3], [1, 2, 3], [4, 5], [3, 2, 1]], False, [1, 2, 3, 1, 2, 3, 4, 5, 3, 2, 1]),
        ([[], [1, 2, 3], [1, 2, 3], [4, 5], [3, 2, 1]], True, [1, 2, 3, 4, 5])
        ],
    ids=(
        'empty-input',
        'empty-lists',
        'keep-duplicates',
        'unique-enabled'
        )
    )
def test_flatten(lists: list[list[Any]], unique: bool, expected: list[Any]) -> None:
    assert tmt.utils.flatten(lists, unique=unique) == expected


@pytest.mark.parametrize(
    ('duration', 'expected'),
    [
        (timedelta(seconds=8), '00:00:08'),
        (timedelta(minutes=6, seconds=8), '00:06:08'),
        (timedelta(hours=4, minutes=6, seconds=8), '04:06:08'),
        (timedelta(days=15, hours=4, minutes=6, seconds=8), '364:06:08'),
        ]
    )
def test_format_duration(duration, expected):
    from tmt.steps.execute import ExecutePlugin

    assert ExecutePlugin.format_duration(duration) == expected


def test_filter_paths(source_dir):
    """ Test if path filtering works correctly """
    paths = filter_paths(source_dir, ['/library'])
    assert len(paths) == 1
    assert paths[0] == source_dir / 'library'

    paths = filter_paths(source_dir, ['bz[235]'])
    assert len(paths) == 3

    paths = filter_paths(source_dir, ['bz[235]', '/tests/bz5'])
    assert len(paths) == 3


@pytest.mark.parametrize(
    ('name', 'allow_slash', 'sanitized'),
    [
        ('foo bar/baz', True, 'foo-bar/baz'),
        ('foo bar/baz', False, 'foo-bar-baz')
        ]
    )
def test_sanitize_name(name: str, allow_slash: bool, sanitized: str) -> None:
    assert tmt.utils.sanitize_name(name, allow_slash=allow_slash) == sanitized


def test_locate_key_origin(id_tree_defined: fmf.Tree) -> None:
    node = id_tree_defined.find('/yes')

    assert tmt.utils.locate_key_origin(node, 'id') is node


def test_locate_key_origin_defined_partially(
        root_logger: tmt.log.Logger,
        id_tree_defined: fmf.Tree) -> None:
    node = id_tree_defined.find('/partial')
    test = tmt.Test(logger=root_logger, node=node)

    assert tmt.utils.locate_key_origin(node, 'id') is test.node


def test_locate_key_origin_not_defined(id_tree_defined: fmf.Tree) -> None:
    node = id_tree_defined.find('/deep/structure/no')

    assert tmt.utils.locate_key_origin(node, 'id').name == '/deep'


def test_locate_key_origin_deeper(id_tree_defined: fmf.Tree) -> None:
    node = id_tree_defined.find('/deep/structure/yes')

    assert tmt.utils.locate_key_origin(node, 'id') is node


def test_locate_key_origin_deeper_not_defined(id_tree_defined: fmf.Tree) -> None:
    node = id_tree_defined.find('/deep/structure/no')

    assert tmt.utils.locate_key_origin(node, 'id') is not node
    assert tmt.utils.locate_key_origin(node, 'id').name == '/deep'


def test_locate_key_origin_empty_defined_root(id_tree_empty: fmf.Tree) -> None:
    node = id_tree_empty.find('/')

    assert tmt.utils.locate_key_origin(node, 'id') is None


def test_locate_key_origin_empty_defined(id_tree_empty: fmf.Tree) -> None:
    node = id_tree_empty.find('/some/structure')

    assert tmt.utils.locate_key_origin(node, 'id') is None


_test_format_value_complex_structure = {
    'foo': [
        'bar',
        'baz',
        {
            'qux': 'fred',
            'xyyzy': [1, False, 17.19]
            },
        'corge'
        ],
    'nested1': {
        'n2': {
            'nest3': True
            },
        'n4': True,
        'n5': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.',  # noqa: E501
        },
    'some boolean': True,
    'empty list': [],
    'nested empty list': [1, False, [], 17.19],
    'single item list': [False],
    'another single item list': ['foo\nbar'],
    }

_test_format_value_big_list = list(range(1, 20))


@pytest.mark.parametrize(
    ('value', 'window_size', 'expected'),
    [
        # NOTE: each test case is prefixed with a comment matching its id
        # in the `ids` list given to `parametrize` below. Keep it that way
        # for easier search.

        # true
        (True, None, 'true'),
        # false
        (False, None, 'false'),
        # list listed
        (
            [1, 2.34, 'foo', False],
            None,
            """
            1
            2.34
            foo
            false
            """
            ),
        # list within huge window
        (
            [1, 2.34, 'foo', False],
            120,
            "'1', '2.34', 'foo' and 'false'"
            ),
        # list within small window
        (
            [1, 2.34, 'foo', False],
            10,
            """
            1
            2.34
            foo
            false
            """
            ),
        # dict
        (
            {'foo': 1, 'bar': 2.34, 'baz': 'qux', 'corge': False},
            None,
            """
            foo: 1
            bar: 2.34
            baz: qux
            corge: false
            """
            ),
        # string
        (
            'foo',
            None,
            'foo'
            ),
        # multiline string
        (
            'foo\nbar\nbaz\n',
            None,
            """
            foo
            bar
            baz
            """
            ),
        # long string
        (
            'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.',  # noqa: E501
            None,
            'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.',  # noqa: E501
        ),
        # long string without a window
        (
            'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.',  # noqa: E501
            72,
            """
            Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod
            tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim
            veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea
            commodo consequat. Duis aute irure dolor in reprehenderit in voluptate
            velit esse cillum dolore eu fugiat nulla pariatur.
            """
        ),
        # complex structure
        (
            _test_format_value_complex_structure,
            None,
            """
            foo:
              - bar
              - baz
              - qux: fred
                xyyzy:
                  - 1
                  - false
                  - 17.19
              - corge
            nested1:
                n2:
                    nest3: true
                n4: true
                n5: Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
            some boolean: true
            empty list:
            nested empty list:
              - 1
              - false
              - []
              - 17.19
            single item list: false
            another single item list:
              - foo
                bar
            """  # noqa: E501
            ),
        # complex structure within small window
        (
            _test_format_value_complex_structure,
            30,
            """
            foo:
              - bar
              - baz
              - qux: fred
                xyyzy:
                  - 1
                  - false
                  - 17.19
              - corge
            nested1:
                n2:
                    nest3: true
                n4: true
                n5:
                    Lorem ipsum dolor
                    sit amet,
                    consectetur
                    adipiscing elit,
                    sed do eiusmod
                    tempor incididunt
                    ut labore et
                    dolore magna
                    aliqua.
            some boolean: true
            empty list:
            nested empty list:
              - 1
              - false
              - []
              - 17.19
            single item list: false
            another single item list:
              - foo
                bar
            """
            ),
        # complex structure within huge window
        (
            _test_format_value_complex_structure,
            120,
            """
            foo:
              - bar
              - baz
              - qux: fred
                xyyzy: '1', 'false' and '17.19'
              - corge
            nested1:
                n2:
                    nest3: true
                n4: true
                n5:
                    Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et
                    dolore magna aliqua.
            some boolean: true
            empty list:
            nested empty list: '1', 'false', [] and '17.19'
            single item list: false
            another single item list:
              - foo
                bar
            """  # noqa: E501
            ),
        # long list
        (
            _test_format_value_big_list,
            None,
            """
            1
            2
            3
            4
            5
            6
            7
            8
            9
            10
            11
            12
            13
            14
            15
            16
            17
            18
            19
            """
            ),
        # long list within small window
        (
            _test_format_value_big_list,
            10,
            """
            1
            2
            3
            4
            5
            6
            7
            8
            9
            10
            11
            12
            13
            14
            15
            16
            17
            18
            19
            """
            ),
        # long list within huge window
        (
            _test_format_value_big_list,
            120,
            """
            '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18' and '19'
            """  # noqa: E501
            )
        ],
    ids=(
        'true',
        'false',
        'list listed',
        'list within huge window',
        'list within small window',
        'dict',
        'string',
        'long string',
        'long string without a window',
        'multiline string',
        'complex structure',
        'complex structure within small window',
        'complex structure within huge window',
        'long list',
        'long list within small window',
        'long list within huge window',
        )
    )
def test_format_value(value: Any, window_size: Optional[int], expected: str) -> None:
    expected = textwrap.dedent(expected).strip('\n')
    actual = tmt.utils.format_value(value, window_size=window_size)

    print('actual vvvvv')
    print(actual)
    print('^^^^^')

    print('expected vvvvv')
    print(expected)
    print('^^^^^')

    assert actual == expected


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('http://example.com', True),
        ('http://example.com/', True),
        ('http://example.com/foo', True),
        ('https://example.com/foo.txt', True),
        ('https://example.com/foo/bar', True),
        ('https://example.com/foo/bar.html?query=1&param=2', True),
        ('protocol://example.com/', True),
        ('', False),
        ('.', False),
        ('/example', False),
        ('example', False),
        ('example.com', False),
        ('example.com/foo', False),
        ],
    ids=(
        'domain-basic',
        'domain-with-slash',
        'domain-with-path',
        'domain-with-file',
        'domain-with-longer-path',
        'domain-with-query',
        'domain-different-protocol',
        'empty-string',
        'dot',
        'absolute-path',
        'string',
        'no-protocol',
        'no-protocol-with-path',
        )
    )
def test_is_url(url: str, expected: bool) -> None:
    assert tmt.utils.is_url(url) == expected


def test_invocation_terminate_process(root_logger: tmt.log.Logger, caplog) -> None:
    from tmt.steps.execute import TestInvocation

    pid = MagicMock(name='process.pid')

    invocation = TestInvocation(
        logger=root_logger,
        phase=MagicMock(name='phase'),
        test=MagicMock(name='test'),
        guest=MagicMock(name='guest'),
        process=MagicMock(name='process')
        )

    invocation.process.pid = pid

    invocation.terminate_process(signal=signal.SIGFPE, logger=root_logger)

    invocation.process.send_signal.assert_called_once_with(signal.SIGFPE)

    assert_log(
        caplog,
        message=MATCH(rf'Terminating process {pid} with {signal.SIGFPE.name}.'),
        levelno=logging.DEBUG)


def test_invocation_terminate_process_not_running_anymore(
        root_logger: tmt.log.Logger, caplog) -> None:
    from tmt.steps.execute import TestInvocation

    invocation = TestInvocation(
        logger=root_logger,
        phase=MagicMock(name='phase'),
        test=MagicMock(name='test'),
        guest=MagicMock(name='guest'),
        process=None
        )

    invocation.terminate_process(signal=signal.SIGFPE, logger=root_logger)

    assert_log(
        caplog,
        message=MATCH(r'Test invocation process cannot be terminated because it is unset.'),
        levelno=logging.DEBUG)
