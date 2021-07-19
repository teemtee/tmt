import os

import pytest

env_vars_parametrization = (
    ("env_name", "value"),
    (
        ("STR", "L"),
        ("INT", "2"),
        ("DOTENV_STR", "dotenv_str"),
        ("DOTENV_INT", "1"),
        ("YAML_STR", "yaml_str"),
        ("YAML_INT", "1"),
        ("YML_STR", "yml_str"),
        ("YML_INT", "1"),
        ),
)


@pytest.mark.with_variables
@pytest.mark.parametrize(*env_vars_parametrization)
def test_environment_file_with_variables(env_name, value):
    assert os.environ[env_name] == value


@pytest.mark.without_variables
@pytest.mark.parametrize(*env_vars_parametrization)
def test_environment_file_without_variables(env_name, value):
    assert env_name not in os.environ
