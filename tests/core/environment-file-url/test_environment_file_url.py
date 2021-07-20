import contextlib
import os
from pathlib import Path
from typing import ContextManager

from click.testing import CliRunner

import tmt.cli

runner = CliRunner()


@contextlib.contextmanager
def change_cwd(path: Path) -> ContextManager[None]:
    origin_dir = str(Path(".").absolute())
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(origin_dir)


def test_environment_file_url_normal_case():
    """Check if fmf definition of environment_file_url works well."""

    with change_cwd(Path(".") / "data"):

        res = runner.invoke(
            tmt.cli.main,
            ["run", "plan", "--name", "/plan/with_fmf_parameter", "-vvvddd"],
            catch_exceptions=False,
            )
        assert res.exit_code == 0
        assert "total: 1 test passed" in res.output


def test_environment_file_url_cli_option():
    """Check if fmf definition of environment_file_url works well."""

    with change_cwd(Path(".") / "data"):

        # ensure variables are missing
        res = runner.invoke(
            tmt.cli.main,
            ["run", "plan", "--name", "/plan/no_vars", "-vvvddd"],
            catch_exceptions=False,
            )
        assert res.exit_code == 1
        assert "KeyError: 'STR'" in res.output

        # provide vars via cli
        res = runner.invoke(
            tmt.cli.main,
            [
                "run",
                "--environment-file-url",
                "https://raw.githubusercontent.com/psss/tmt/22a46a4a6760517e3eadbbff0c9bebdb95442760/tests/core/env/data/vars.yaml",
                "plan",
                "--name",
                "/plan/no_vars",
                "-vvvddd",
                ],
            catch_exceptions=False,
            )
        assert res.exit_code == 0
        assert "total: 1 test passed" in res.output
