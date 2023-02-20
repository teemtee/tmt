# coding: utf-8

import datetime
import queue
import re
import threading
import time
import unittest
import unittest.mock
from typing import Tuple

import py
import pytest

import tmt
import tmt.log
import tmt.plugins
import tmt.steps.discover
import tmt.utils
from tmt.utils import (Command, Common, GeneralError, Path, ShellScript,
                       StructuredField, StructuredFieldError,
                       WaitingIncomplete, WaitingTimedOutError, _CommonBase,
                       duration_to_seconds, listify, public_git_url,
                       validate_git_status, wait)

run = Common(logger=tmt.log.Logger.create(verbose=0, debug=0, quiet=False)).run


@pytest.fixture
def local_git_repo(tmpdir: py.path.local) -> Path:
    origin = Path(str(tmpdir)) / 'origin'
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


@pytest.fixture
def origin_and_local_git_repo(local_git_repo: Path) -> Tuple[Path, Path]:
    top_dir = local_git_repo.parent
    fork_dir = top_dir / 'fork'
    run(ShellScript(f'git clone {local_git_repo} {fork_dir}').to_shell_command(),
        cwd=top_dir)
    run(ShellScript('git config --local user.email lzachar@redhat.com').to_shell_command(),
        cwd=fork_dir)
    run(ShellScript('git config --local user.name LZachar').to_shell_command(),
        cwd=fork_dir)
    return local_git_repo, fork_dir


def test_public_git_url():
    """ Verify url conversion """
    examples = [
        {
            'original': 'git@github.com:teemtee/tmt.git',
            'expected': 'https://github.com/teemtee/tmt.git',
            }, {
            'original': 'ssh://psplicha@pkgs.devel.redhat.com/tests/bash',
            'expected': 'git://pkgs.devel.redhat.com/tests/bash',
            }, {
            'original': 'git+ssh://psplicha@pkgs.devel.redhat.com/tests/bash',
            'expected': 'git://pkgs.devel.redhat.com/tests/bash',
            }, {
            'original': 'ssh://pkgs.devel.redhat.com/tests/bash',
            'expected': 'git://pkgs.devel.redhat.com/tests/bash',
            }, {
            'original': 'git+ssh://psss@pkgs.fedoraproject.org/tests/shell',
            'expected': 'https://pkgs.fedoraproject.org/tests/shell',
            }, {
            'original': 'ssh://psss@pkgs.fedoraproject.org/tests/shell',
            'expected': 'https://pkgs.fedoraproject.org/tests/shell',
            }, {
            'original': 'ssh://git@pagure.io/fedora-ci/metadata.git',
            'expected': 'https://pagure.io/fedora-ci/metadata.git',
            },
        ]
    for example in examples:
        assert public_git_url(example['original']) == example['expected']


def test_listify():
    """ Check listify functionality """
    assert listify(['abc']) == ['abc']
    assert listify('abc') == ['abc']
    assert listify('a b c') == ['a b c']
    assert listify('a b c', split=True) == ['a', 'b', 'c']
    assert listify(dict(a=1, b=2)) == dict(a=[1], b=[2])
    assert listify(dict(a=1, b=2), keys=['a']) == dict(a=[1], b=2)


def test_config():
    """ Config smoke test """
    run = Path('/var/tmp/tmt/test')
    config1 = tmt.utils.Config()
    config1.last_run = run
    config2 = tmt.utils.Config()
    assert config2.last_run.resolve() == run.resolve()


def test_last_run_race(tmpdir, monkeypatch):
    """ Race in last run symlink should't be fatal """
    monkeypatch.setattr(tmt.utils, 'CONFIG_PATH', Path(str(tmpdir.mkdir('config'))))
    mock_logger = unittest.mock.MagicMock()
    monkeypatch.setattr(tmt.utils.log, 'warning', mock_logger)
    config = tmt.utils.Config()
    results = queue.Queue()
    threads = []

    def create_last_run(config, counter):
        try:
            val = config.last_run = Path(str(tmpdir.mkdir(f"run-{counter}")))
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
    for t in threads:
        value = results.get()
        if isinstance(value, Exception):
            # Print exception for logging
            print(value)
            all_good = False
    assert all_good
    # Getting into race is not certain, do not assert
    # assert mock_logger.called
    assert config.last_run, "Some run was stored as last run"


def test_workdir_env_var(tmpdir, monkeypatch, root_logger):
    """ Test TMT_WORKDIR_ROOT environment variable """
    # Cannot use monkeypatch.context() as it is not present for CentOS Stream 8
    monkeypatch.setenv('TMT_WORKDIR_ROOT', tmpdir)
    common = Common(logger=root_logger)
    common._workdir_init()
    monkeypatch.delenv('TMT_WORKDIR_ROOT')
    assert common.workdir == Path(f'{tmpdir}/run-001')


def test_workdir_root_full(tmpdir, monkeypatch, root_logger):
    """ Raise if all ids lower than WORKDIR_MAX are exceeded """
    monkeypatch.setattr(tmt.utils, 'WORKDIR_ROOT', Path(str(tmpdir)))
    monkeypatch.setattr(tmt.utils, 'WORKDIR_MAX', 1)
    possible_workdir = Path(str(tmpdir)) / 'run-001'
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


def test_workdir_root_race(tmpdir, monkeypatch, root_logger):
    """ Avoid race in workdir creation """
    monkeypatch.setattr(tmt.utils, 'WORKDIR_ROOT', Path(str(tmpdir)))
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
    for t in threads:
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
    with pytest.raises(tmt.utils.SpecificationError):
        duration_to_seconds('bad')


class test_structured_field(unittest.TestCase):
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
        self.assertEqual(inited0.save(), text0)
        self.assertEqual(loaded0.save(), text0)
        # Version 1
        text1 = "\n".join([
                self.header,
                self.start, self.sections, self.end,
                self.footer])
        inited1 = StructuredField(text1)
        loaded1 = StructuredField()
        loaded1.load(text1)
        self.assertEqual(inited1.save(), text1)
        self.assertEqual(loaded1.save(), text1)
        # Common checks
        for field in [inited0, loaded0, inited1, loaded1]:
            self.assertEqual(field.header(), self.header)
            self.assertEqual(field.footer(), self.footer)
            self.assertEqual(field.sections(), ["one", "two", "three"])
            self.assertEqual(field.get("one"), "1\n")
            self.assertEqual(field.get("two"), "2\n")
            self.assertEqual(field.get("three"), "3\n")

    def test_no_header(self):
        """ No header """
        # Version 0
        text0 = "\n".join([self.sections, self.zeroend, self.footer])
        field0 = StructuredField(text0, version=0)
        self.assertEqual(field0.save(), text0)
        # Version 1
        text1 = "\n".join(
                [self.start, self.sections, self.end, self.footer])
        field1 = StructuredField(text1)
        self.assertEqual(field1.save(), text1)
        # Common checks
        for field in [field0, field1]:
            self.assertEqual(field.header(), "")
            self.assertEqual(field.footer(), self.footer)
            self.assertEqual(field.get("one"), "1\n")
            self.assertEqual(field.get("two"), "2\n")
            self.assertEqual(field.get("three"), "3\n")

    def test_no_footer(self):
        """ No footer """
        # Version 0
        text0 = "\n".join([self.header, self.sections, self.zeroend])
        field0 = StructuredField(text0, version=0)
        self.assertEqual(field0.save(), text0)
        # Version 1
        text1 = "\n".join(
                [self.header, self.start, self.sections, self.end])
        field1 = StructuredField(text1)
        self.assertEqual(field1.save(), text1)
        # Common checks
        for field in [field0, field1]:
            self.assertEqual(field.header(), self.header)
            self.assertEqual(field.footer(), "")
            self.assertEqual(field.get("one"), "1\n")
            self.assertEqual(field.get("two"), "2\n")
            self.assertEqual(field.get("three"), "3\n")

    def test_just_sections(self):
        """ Just sections """
        # Version 0
        text0 = "\n".join([self.sections, self.zeroend])
        field0 = StructuredField(text0, version=0)
        self.assertEqual(field0.save(), text0)
        # Version 1
        text1 = "\n".join([self.start, self.sections, self.end])
        field1 = StructuredField(text1)
        self.assertEqual(field1.save(), text1)
        # Common checks
        for field in [field0, field1]:
            self.assertEqual(field.header(), "")
            self.assertEqual(field.footer(), "")
            self.assertEqual(field.get("one"), "1\n")
            self.assertEqual(field.get("two"), "2\n")
            self.assertEqual(field.get("three"), "3\n")

    def test_plain_text(self):
        """ Plain text """
        text = "Some plain text.\n"
        field0 = StructuredField(text, version=0)
        field1 = StructuredField(text)
        for field in [field0, field1]:
            self.assertEqual(field.header(), text)
            self.assertEqual(field.footer(), "")
            self.assertEqual(field.save(), text)
            self.assertEqual(list(field), [])
            self.assertEqual(bool(field), False)

    def test_missing_end_tag(self):
        """ Missing end tag """
        text = "\n".join([self.header, self.sections, self.footer])
        self.assertRaises(StructuredFieldError, StructuredField, text, 0)

    def test_broken_field(self):
        """ Broken field"""
        text = "[structured-field-start]"
        self.assertRaises(StructuredFieldError, StructuredField, text)

    def test_set_content(self):
        """ Set section content """
        field0 = StructuredField(version=0)
        field1 = StructuredField()
        for field in [field0, field1]:
            field.set("one", "1")
            self.assertEqual(field.get("one"), "1\n")
            field.set("two", "2")
            self.assertEqual(field.get("two"), "2\n")
            field.set("three", "3")
            self.assertEqual(field.get("three"), "3\n")
        self.assertEqual(field0.save(), "\n".join(
            [self.sections, self.zeroend]))
        self.assertEqual(field1.save(), "\n".join(
            [self.start, self.sections, self.end]))

    def test_remove_section(self):
        """ Remove section """
        field0 = StructuredField(
            "\n".join([self.sections, self.zeroend]), version=0)
        field1 = StructuredField(
            "\n".join([self.start, self.sections, self.end]))
        for field in [field0, field1]:
            field.remove("one")
            field.remove("two")
        self.assertEqual(
            field0.save(), "\n".join([self.three, self.zeroend]))
        self.assertEqual(
            field1.save(), "\n".join([self.start, self.three, self.end]))

    def test_section_tag_escaping(self):
        """ Section tag escaping """
        field = StructuredField()
        field.set("section", "\n[content]\n")
        reloaded = StructuredField(field.save())
        self.assertTrue("section" in reloaded)
        self.assertTrue("content" not in reloaded)
        self.assertEqual(reloaded.get("section"), "\n[content]\n")

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
        self.assertEqual(parent.get("name"), "Parent Name\n")
        self.assertEqual(child.get("name"), "Child Name\n")
        self.assertEqual(grandchild.get("name"), "Grand Child\n")

    def test_section_tags_in_header(self):
        """ Section tags in header """
        field = StructuredField("\n".join(
            ["[something]", self.start, self.one, self.end]))
        self.assertTrue("something" not in field)
        self.assertTrue("one" in field)
        self.assertEqual(field.get("one"), "1\n")

    def test_empty_section(self):
        """ Empty section """
        field = StructuredField()
        field.set("section", "")
        reloaded = StructuredField(field.save())
        self.assertEqual(reloaded.get("section"), "")

    def test_section_item_get(self):
        """ Get section item """
        text = "\n".join([self.start, "[section]\nx = 3\n", self.end])
        field = StructuredField(text)
        self.assertEqual(field.get("section", "x"), "3")

    def test_section_item_set(self):
        """ Set section item """
        text = "\n".join([self.start, "[section]\nx = 3\n", self.end])
        field = StructuredField()
        field.set("section", "3", "x")
        self.assertEqual(field.save(), text)

    def test_section_item_remove(self):
        """ Remove section item """
        text = "\n".join(
            [self.start, "[section]\nx = 3\ny = 7\n", self.end])
        field = StructuredField(text)
        field.remove("section", "x")
        self.assertEqual(field.save(), "\n".join(
            [self.start, "[section]\ny = 7\n", self.end]))

    def test_unicode_header(self):
        """ Unicode text in header """
        text = u"Už abychom měli unicode jako defaultní kódování!"
        field = StructuredField(text)
        field.set("section", "content")
        self.assertTrue(text in field.save())

    def test_unicode_section_content(self):
        """ Unicode in section content """
        chars = u"ěščřžýáíéů"
        text = "\n".join([self.start, "[section]", chars, self.end])
        field = StructuredField(text)
        self.assertEqual(field.get("section").strip(), chars)

    def test_unicode_section_name(self):
        """ Unicode in section name """
        chars = u"ěščřžýáíéů"
        text = "\n".join([self.start, u"[{0}]\nx".format(chars), self.end])
        field = StructuredField(text)
        self.assertEqual(field.get(chars).strip(), "x")

    def test_header_footer_modify(self):
        """ Modify header & footer """
        original = StructuredField()
        original.set("field", "field-content")
        original.header("header-content\n")
        original.footer("footer-content\n")
        copy = StructuredField(original.save())
        self.assertEqual(copy.header(), "header-content\n")
        self.assertEqual(copy.footer(), "footer-content\n")

    def test_trailing_whitespace(self):
        """ Trailing whitespace """
        original = StructuredField()
        original.set("name", "value")
        # Test with both space and tab appended after the section tag
        for char in [" ", "\t"]:
            spaced = re.sub(r"\]\n", "]{0}\n".format(char), original.save())
            copy = StructuredField(spaced)
            self.assertEqual(original.get("name"), copy.get("name"))

    def test_carriage_returns(self):
        """ Carriage returns """
        text1 = "\n".join([self.start, self.sections, self.end])
        text2 = re.sub(r"\n", "\r\n", text1)
        field1 = StructuredField(text1)
        field2 = StructuredField(text2)
        self.assertEqual(field1.save(), field2.save())

    def test_multiple_values(self):
        """ Multiple values """
        # Reading multiple values
        section = "[section]\nkey=val1 # comment\nkey = val2\n key = val3 "
        text = "\n".join([self.start, section, self.end])
        field = StructuredField(text, multi=True)
        self.assertEqual(
            field.get("section", "key"), ["val1", "val2", "val3"])
        # Writing multiple values
        values = ['1', '2', '3']
        field = StructuredField(multi=True)
        field.set("section", values, "key")
        self.assertEqual(field.get("section", "key"), values)
        self.assertTrue("key = 1\nkey = 2\nkey = 3" in field.save())
        # Remove multiple values
        field.remove("section", "key")
        self.assertTrue("key = 1\nkey = 2\nkey = 3" not in field.save())
        self.assertRaises(
            StructuredFieldError, field.get, "section", "key")


def test_run_interactive_not_joined(tmpdir, root_logger):
    stdout, stderr = Common(logger=root_logger)._run(
        "echo abc; echo def >2", shell=True, interactive=True, cwd=str(tmpdir), env={}, log=None)
    assert stdout is None
    assert stderr is None


def test_run_interactive_joined(tmpdir, root_logger):
    stdout, _ = Common(logger=root_logger)._run(
        "echo abc; echo def >2",
        shell=True,
        interactive=True,
        cwd=str(tmpdir),
        env={},
        join=True,
        log=None)
    assert stdout is None


def test_run_not_joined_stdout(root_logger):
    stdout, _ = Common(
        logger=root_logger)._run(
        Command(
            "ls", "/"), shell=False, cwd=".", env={}, log=None)
    assert "sbin" in stdout


def test_run_not_joined_stderr(root_logger):
    _, stderr = Common(logger=root_logger)._run(
        ShellScript("ls non_existing || true").to_shell_command(),
        shell=False,
        cwd=".",
        env={},
        log=None)
    assert "ls: cannot access" in stderr


def test_run_joined(root_logger):
    stdout, _ = Common(logger=root_logger)._run(
        ShellScript("ls non_existing / || true").to_shell_command(),
        shell=False,
        cwd=".",
        env={},
        log=None,
        join=True)
    assert "ls: cannot access" in stdout
    assert "sbin" in stdout


def test_run_big(root_logger):
    stdout, _ = Common(logger=root_logger)._run(
        ShellScript("""for NUM in {1..100}; do LINE="$LINE n"; done; for NUM in {1..1000}; do echo $LINE; done""").to_shell_command(),  # noqa: E501
        shell=False,
        cwd=".",
        env={},
        log=None,
        join=True)
    assert "n n" in stdout
    assert len(stdout) == 200000


def test_get_distgit_handler():
    for wrong_remotes in [[], ["blah"]]:
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
        "remote.origin.url https://<redacted_credentials>@gitlab.com/redhat/rhel/rpms/osbuild.git",  # noqa: E501
    ])
    assert isinstance(returned_object, tmt.utils.RedHatGitlab)


def test_get_distgit_handler_explicit():
    instance = tmt.utils.get_distgit_handler(usage_name='redhatgitlab')
    assert instance.__class__.__name__ == 'RedHatGitlab'


def test_FedoraDistGit(tmpdir):
    # Fake values, production hash is too long
    path = Path(str(tmpdir))
    path.joinpath('sources').write_text('SHA512 (fn-1.tar.gz) = 09af\n')
    path.joinpath('tmt.spec').write_text('')
    fedora_sources_obj = tmt.utils.FedoraDistGit()
    assert [("https://src.fedoraproject.org/repo/pkgs/rpms/tmt/fn-1.tar.gz/sha512/09af/fn-1.tar.gz",  # noqa: E501
            "fn-1.tar.gz")] == fedora_sources_obj.url_and_name(cwd=path)


class Test_validate_git_status:
    @pytest.mark.parametrize("use_path",
                             [False, True], ids=["without path", "with path"])
    def test_all_good(
            cls,
            origin_and_local_git_repo: Tuple[Path, Path],
            use_path: bool,
            root_logger):
        # No need to modify origin, ignoring it
        mine = origin_and_local_git_repo[1]

        # In local repo:
        # Init tmt and add test
        if use_path:
            fmf_root = mine / 'fmf_root'
        else:
            fmf_root = mine
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

    def test_no_remote(cls, local_git_repo: Path, root_logger):
        tmpdir = local_git_repo
        tmt.Tree.init(logger=root_logger, path=tmpdir, template=None, force=None)
        tmpdir.joinpath('main.fmf').write_text('test: echo')
        run(ShellScript('git add main.fmf .fmf/version').to_shell_command(),
            cwd=tmpdir)
        run(ShellScript('git commit -m initial_commit').to_shell_command(),
            cwd=tmpdir)

        test = tmt.Tree(logger=root_logger, path=tmpdir).tests()[0]
        val, msg = validate_git_status(test)
        assert not val
        assert "Failed to get remote branch" in msg

    def test_untracked_fmf_root(cls, local_git_repo: Path, root_logger):
        # local repo is enough since this can't get passed 'is pushed' check
        tmt.Tree.init(logger=root_logger, path=local_git_repo, template=None, force=None)
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

    @pytest.mark.parametrize("use_path",
                             [False, True], ids=["without path", "with path"])
    def test_local_changes(
            cls,
            origin_and_local_git_repo: Tuple[Path, Path],
            use_path,
            root_logger):
        origin, mine = origin_and_local_git_repo

        if use_path:
            fmf_root = origin / 'fmf_root'
        else:
            fmf_root = origin
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

    def test_not_pushed(cls, origin_and_local_git_repo: Tuple[Path, Path], root_logger):
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

        raise WaitingIncomplete()

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
        side_effect=WaitingIncomplete)

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


def test_import_member():
    klass = tmt.plugins.import_member('tmt.steps.discover', 'Discover')

    assert klass is tmt.steps.discover.Discover


def test_import_member_no_such_module():
    with pytest.raises(
            tmt.utils.GeneralError,
            match=r"Failed to import module 'tmt\.steps\.nope_does_not_exist'."):
        tmt.plugins.import_member('tmt.steps.nope_does_not_exist', 'Discover')


def test_import_member_no_such_class():
    with pytest.raises(
            tmt.utils.GeneralError,
            match=r"No such member 'NopeDoesNotExist' in module 'tmt\.steps\.discover'."):
        tmt.plugins.import_member('tmt.steps.discover', 'NopeDoesNotExist')


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
