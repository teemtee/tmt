import os

import pytest

env_vars_parametrization = ()


@pytest.mark.parametrize(
    ("env_name", "value"),
    (
        ("STR", "O"),
        ("INT", "0"),
        ),
)
def test_environment_file_url(env_name, value):
    assert os.environ[env_name] == value
