from typing import TYPE_CHECKING

from tests import jq_all, with_cwd

from tmt.utils import Path, from_yaml

if TYPE_CHECKING:
    from tests import RunTmt


TEST_DIR = Path(__file__).absolute().parent
DATA_DIR = TEST_DIR / 'data/plan'
POLICIES_DIR = TEST_DIR / 'policies'


@with_cwd(DATA_DIR)
def test_export_modified_plan(run_tmt: 'RunTmt') -> None:
    """
    Verify a plan export is affected by the policy.

    .. note::

        Not doing anything complex, test-level policy tests cover plenty
        of policy instructions and behavior. Focusing on plan-specific
        modifications only.
    """

    result = run_tmt(
        '-vv',
        'plan',
        'export',
        '--policy-file',
        POLICIES_DIR / 'plan/plan.yaml',
    )

    assert f"Apply tmt policy '{POLICIES_DIR}/plan/plan.yaml' to plans." in result.stderr

    plans_exported = from_yaml(result.stdout)

    assert jq_all(plans_exported, '.[] | .discover') == [None], "Verify that discover key is empty"

    assert jq_all(plans_exported, '.[] | .prepare | .[] | [.how, .order]') == [
        ['feature', 17],
        ['shell', None],
    ], 'Verify that prepare step contains two phases'

    assert jq_all(plans_exported, '.[] | .contact') == [["xyzzy"]], (
        'Verify that contact key was populated'
    )


@with_cwd(DATA_DIR)
def test_run_modified_plan(run_tmt: 'RunTmt') -> None:
    """
    Verify a run is affected by the policy.
    """

    result = run_tmt('-vv', 'run', '-a', '--policy-file', POLICIES_DIR / 'plan/simple.yaml')

    assert f"Apply tmt policy '{POLICIES_DIR}/plan/simple.yaml' to plans." in result.stderr
    assert "No tests found, finishing plan." in result.stderr
