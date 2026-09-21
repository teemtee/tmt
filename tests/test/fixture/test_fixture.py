from typing import TYPE_CHECKING

import pytest
from tests import TmtCliRunOptions, run_plan, with_fmf_root

from tmt._compat.pathlib import Path
from tmt.utils import yaml_to_list

if TYPE_CHECKING:
    from tests import RunTmt

TEST_DIR = Path(__file__).absolute().parent
DATA_DIR = TEST_DIR / "data"


@pytest.fixture(autouse=True)
def provision_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMT_ALLOW_UNSAFE_BEHAVIOR", "provision/local")


@with_fmf_root(DATA_DIR)
@pytest.mark.usefixtures("fmf_root")
@run_plan("/plan/select_only_test")
def test_basic_property(
    run_tmt: "RunTmt",
    run_id: Path,
    run_plan: str,
    _tmt_cli_run_options: TmtCliRunOptions,
) -> None:
    _tmt_cli_run_options.discover = []
    result = run_tmt()
    assert result.exit_code == 0
    plan_path = run_id / Path(run_plan).unrooted()
    assert plan_path.exists()
    tests_yaml = plan_path / "discover/tests.yaml"
    tests = yaml_to_list(tests_yaml.read_text())
    assert len(tests) == 3
    assert tests[0]["name"] == "/test/setup"
    assert tests[1]["name"] == "/test/main_test"
    assert tests[2]["name"] == "/test/cleanup"


@with_fmf_root(DATA_DIR)
@pytest.mark.usefixtures("fmf_root")
@run_plan("/plan/fail_setup")
def test_failed_setup(
    run_tmt: "RunTmt",
    run_id: Path,
    run_plan: str,
    _tmt_cli_run_options: TmtCliRunOptions,
) -> None:
    result = run_tmt()
    assert result.exit_code == 1
    plan_path = run_id / Path(run_plan).unrooted()
    assert plan_path.exists()
    results_yaml = plan_path / "execute/results.yaml"
    results = yaml_to_list(results_yaml.read_text())
    setup_result = next(r for r in results if r["name"] == "/test/setup")
    assert setup_result["result"] == "fail"
    main_result = next(r for r in results if r["name"] == "/test/main_test")
    assert main_result["result"] == "skip"
    assert len(main_result["note"]) == 1
    assert "Setup fixture '/test/setup' failed!" in main_result["note"]
    # TODO: What should the cleanup test be here?
    cleanup_result = next(r for r in results if r["name"] == "/test/cleanup")
    assert cleanup_result["result"] == "fail"


@with_fmf_root(DATA_DIR)
@pytest.mark.usefixtures("fmf_root")
@run_plan("/plan/skip_setup")
def test_skip_setup(
    run_tmt: "RunTmt",
    run_id: Path,
    run_plan: str,
    _tmt_cli_run_options: TmtCliRunOptions,
) -> None:
    result = run_tmt()
    assert result.exit_code == 1
    plan_path = run_id / Path(run_plan).unrooted()
    assert plan_path.exists()
    results_yaml = plan_path / "execute/results.yaml"
    results = yaml_to_list(results_yaml.read_text())
    setup_result = next(r for r in results if r["name"] == "/test/setup")
    assert setup_result["result"] == "skip"
    main_result = next(r for r in results if r["name"] == "/test/main_test")
    assert main_result["result"] == "skip"
    assert len(main_result["note"]) == 1
    assert "Setup fixture '/test/setup' was skipped." in main_result["note"]
    # TODO: What should the cleanup test be here?
    cleanup_result = next(r for r in results if r["name"] == "/test/cleanup")
    assert cleanup_result["result"] == "fail"
