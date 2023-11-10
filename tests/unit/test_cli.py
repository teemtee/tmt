import dataclasses
import os
import shutil
import sys
import tempfile

import _pytest.monkeypatch
import pytest

import tmt.cli
import tmt.log

from .. import CliRunner

# Prepare path to examples
PATH = os.path.dirname(os.path.realpath(__file__))


def example(name):
    """ Return path to given example """
    return os.path.join(PATH, "../../examples/", name)


runner = CliRunner()


def test_mini():
    """ Minimal smoke test """
    tmp = tempfile.mkdtemp()
    result = runner.invoke(
        tmt.cli.main,
        ['--root', example('mini'), 'run', '-i', tmp, '-dv', 'discover'])
    assert result.exit_code == 0
    assert 'Found 1 plan.' in result.output
    assert '1 test selected' in result.output
    assert '/ci' in result.output
    shutil.rmtree(tmp)


def test_init():
    """ Tree initialization """
    tmp = tempfile.mkdtemp()
    original_directory = os.getcwd()
    os.chdir(tmp)
    result = runner.invoke(tmt.cli.main, ['init'])
    assert 'initialized' in result.output
    result = runner.invoke(tmt.cli.main, ['init'])
    assert 'already exists' in result.output
    result = runner.invoke(tmt.cli.main, ['init', '--template', 'mini'])
    assert 'plans/example' in result.output
    result = runner.invoke(tmt.cli.main, ['init', '--template', 'mini'])
    assert result.exception
    result = runner.invoke(tmt.cli.main, ['init', '--template', 'full',
                                          '--force'])
    assert 'overwritten' in result.output
    # tmt init --template mini in a clean directory
    os.system('rm -rf .fmf *')
    result = runner.invoke(tmt.cli.main, ['init', '--template', 'mini'])
    assert 'plans/example' in result.output
    # tmt init --template full in a clean directory
    os.system('rm -rf .fmf *')
    result = runner.invoke(tmt.cli.main, ['init', '--template', 'full'])
    assert 'tests/example' in result.output
    os.chdir(original_directory)
    shutil.rmtree(tmp)


def test_create():
    """ Test, plan and story creation """
    # Create a test directory
    tmp = tempfile.mkdtemp()
    original_directory = os.getcwd()
    os.chdir(tmp)
    # Commands to test
    commands = [
        'init',
        'test create -t beakerlib test',
        'test create -t shell test',
        'plan create -t mini test',
        'plan create -t full test',
        'story create -t mini test',
        'story create -t full test',
        ]
    for command in commands:
        result = runner.invoke(tmt.cli.main, command.split())
        assert result.exit_code == 0
        os.system('rm -rf *')
    # Test directory cleanup
    os.chdir(original_directory)
    shutil.rmtree(tmp)


def test_step():
    """ Select desired step"""
    for step in ['discover', 'provision', 'prepare']:
        tmp = tempfile.mkdtemp()
        result = runner.invoke(
            tmt.cli.main, ['--root', example('local'), 'run', '-i', tmp, step])
        assert result.exit_code == 0
        assert step in result.output
        assert 'finish' not in result.output
        shutil.rmtree(tmp)


def test_step_execute():
    """ Test execute step"""
    tmp = tempfile.mkdtemp()
    step = 'execute'

    result = runner.invoke(
        tmt.cli.main, ['--root', example('local'), 'run', '-i', tmp, step])

    # Test execute empty with discover output missing
    assert result.exit_code != 0
    assert isinstance(result.exception, tmt.utils.GeneralError)
    assert len(result.exception.causes) == 1
    assert isinstance(result.exception.causes[0], tmt.utils.ExecuteError)
    assert step in result.output
    assert 'provision' not in result.output
    shutil.rmtree(tmp)


def test_systemd():
    """ Check systemd example """
    result = runner.invoke(
        tmt.cli.main, ['--root', example('systemd'), 'plan'])
    assert result.exit_code == 0
    assert 'Found 2 plans' in result.output
    result = runner.invoke(
        tmt.cli.main, ['--root', example('systemd'), 'plan', 'show'])
    assert result.exit_code == 0
    assert 'Tier two functional tests' in result.output


@dataclasses.dataclass
class DecideColorizationTestcase:
    """ A single test case for :py:func:`tmt.log.decide_colorization` """

    # Name of the testcase and expected outcome of decide_colorization()
    name: str
    expected: tuple[bool, bool]

    # Testcase environment setup to perform before calling decide_colorization()
    set_no_color_option: bool = False
    set_force_color_option: bool = False
    set_no_color_envvar: bool = False
    set_tmt_no_color_envvar: bool = False
    set_tmt_force_color_envvar: bool = False
    simulate_tty: bool = False


_DECIDE_COLORIZATION_TESTCASES = [
    # With TTY simulated
    DecideColorizationTestcase(
        'tty, autodetection',
        (True, True),
        simulate_tty=True),
    DecideColorizationTestcase(
        'tty, disable with option',
        (False, False),
        set_no_color_option=True,
        simulate_tty=True),
    DecideColorizationTestcase(
        'tty, disable with NO_COLOR',
        (False, False),
        set_no_color_envvar=True,
        simulate_tty=True),
    DecideColorizationTestcase(
        'tty, disable with TMT_NO_COLOR',
        (False, False),
        set_tmt_no_color_envvar=True,
        simulate_tty=True),
    DecideColorizationTestcase(
        'tty, force with option',
        (True, True),
        set_force_color_option=True,
        simulate_tty=True),
    DecideColorizationTestcase(
        'tty, force with TMT_FORCE_COLOR',
        (True, True),
        set_tmt_force_color_envvar=True,
        simulate_tty=True),

    DecideColorizationTestcase(
        'tty, force with TMT_FORCE_COLOR over NO_COLOR',
        (True, True),
        set_tmt_force_color_envvar=True,
        set_no_color_envvar=True),
    DecideColorizationTestcase(
        'tty, force with TMT_FORCE_COLOR over --no-color',
        (True, True),
        set_tmt_force_color_envvar=True,
        set_no_color_option=True),

    # With TTY not simulated, streams are captured
    DecideColorizationTestcase(
        'not tty, autodetection',
        (False, False)),
    DecideColorizationTestcase(
        'not tty, disable with option',
        (False, False),
        set_no_color_option=True),
    DecideColorizationTestcase(
        'not tty, disable with NO_COLOR',
        (False, False),
        set_no_color_envvar=True),
    DecideColorizationTestcase(
        'not tty, disable with TMT_NO_COLOR',
        (False, False),
        set_tmt_no_color_envvar=True),
    DecideColorizationTestcase(
        'not tty, force with option',
        (True, True),
        set_force_color_option=True),
    DecideColorizationTestcase(
        'not tty, force with TMT_FORCE_COLOR',
        (True, True),
        set_tmt_force_color_envvar=True),

    DecideColorizationTestcase(
        'not tty, force with TMT_FORCE_COLOR over NO_COLOR',
        (True, True),
        set_tmt_force_color_envvar=True,
        set_tmt_no_color_envvar=True),
    DecideColorizationTestcase(
        'not tty, force with TMT_FORCE_COLOR over --no-color',
        (True, True),
        set_tmt_force_color_envvar=True,
        set_no_color_option=True),
    ]


@pytest.mark.parametrize(
    'testcase',
    list(_DECIDE_COLORIZATION_TESTCASES),
    ids=[testcase.name for testcase in _DECIDE_COLORIZATION_TESTCASES]
    )
def test_decide_colorization(
        testcase: DecideColorizationTestcase,
        monkeypatch: _pytest.monkeypatch.MonkeyPatch
        ) -> None:
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.delenv('TMT_NO_COLOR', raising=False)
    monkeypatch.delenv('TMT_FORCE_COLOR', raising=False)

    no_color = bool(testcase.set_no_color_option)
    force_color = bool(testcase.set_force_color_option)

    if testcase.set_no_color_envvar:
        monkeypatch.setenv('NO_COLOR', '')

    if testcase.set_tmt_no_color_envvar:
        monkeypatch.setenv('TMT_NO_COLOR', '')

    if testcase.set_tmt_force_color_envvar:
        monkeypatch.setenv('TMT_FORCE_COLOR', '')

    monkeypatch.setattr(sys.stdout, 'isatty', lambda: testcase.simulate_tty)
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: testcase.simulate_tty)

    assert tmt.log.decide_colorization(no_color, force_color) == testcase.expected
