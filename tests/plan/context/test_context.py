from typing import TYPE_CHECKING

from tests import with_cwd

from tmt.utils import Path

if TYPE_CHECKING:
    from tests import RunTmt


TEST_DIR = Path(__file__).absolute().parent
DATA_DIR = TEST_DIR / 'data'


@with_cwd(dirname='data')
def test_plan_with_good_context(run_tmt: 'RunTmt') -> None:
    """
    Plan with a good context
    """

    result = run_tmt('-c', 'distro=rhel9', '-c', 'arch=aarch64,x86_64', 'plan', 'show', 'good')

    assert "foo: bar" in result.stdout
    assert "baz: 'qux' and 'fred'" in result.stdout
    assert "distro: rhel9" in result.stdout
    assert "arch: 'aarch64' and 'x86_64'" in result.stdout


@with_cwd(dirname='data')
def test_plan_with_bad_context(run_tmt: 'RunTmt') -> None:
    """
    Plan with a bad context
    """

    result = run_tmt('-c', 'distro=rhel9', '-c', 'arch=aarch64,x86_64', 'plan', 'show', 'bad')

    assert "distro: rhel9" in result.stdout
    assert "arch: 'aarch64' and 'x86_64'" in result.stdout


@with_cwd(dirname='data')
def test_plan_with_good_context_and_bad_command_line(run_tmt: 'RunTmt') -> None:
    """
    Plan with a good context, overwritten by command line
    """

    result = run_tmt(
        '-c',
        'distro=rhel9',
        '-c',
        'arch=aarch64,x86_64',
        '-c',
        'baz=something,different',
        'plan',
        'show',
        'good',
    )

    assert "foo: bar" in result.stdout
    assert "baz: 'something' and 'different'" in result.stdout
    assert "distro: rhel9" in result.stdout
    assert "arch: 'aarch64' and 'x86_64'" in result.stdout


@with_cwd(dirname='data')
def test_plan_with_broken_values(run_tmt: 'RunTmt') -> None:
    """
    Plan with broken values
    """

    result = run_tmt(
        '-c', 'distro=rhel9', '-c', 'arch=aarch64,x86_64', 'plan', 'show', 'bad-values'
    )

    assert "foo: foo" in result.stdout
    assert "bar: 1" in result.stdout
    assert "baz: False" in result.stdout
    assert "dud: {'how': 'about'}" in result.stdout
    assert "distro: rhel9" in result.stdout
    assert "arch: 'aarch64' and 'x86_64'" in result.stdout
    assert (
        "warn: /bad-values:context.baz - False is not valid under any of the given schemas"
        in result.stderr
    )
    assert (
        "warn: /bad-values:context.dud - {'how': 'about'} is not valid under any of the given schemas"  # noqa: E501
        in result.stderr
    )
    assert (
        "warn: /bad-values:context.bar - 1 is not valid under any of the given schemas"
        in result.stderr
    )
