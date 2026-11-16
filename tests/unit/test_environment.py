from tmt.utils.environment import Environment, EnvVar, EnvVarValue


class ENV_TMT_TEST(EnvVar):  # noqa: N801
    name = 'TMT_TEST'
    scope = EnvVar.Scope.TEST


def test_environment_setdefault_normalizes_envvar_key() -> None:
    environment = Environment()

    assert environment.setdefault(ENV_TMT_TEST, EnvVarValue('value')) == 'value'
    assert environment == {'TMT_TEST': 'value'}
    assert environment.get(ENV_TMT_TEST) == 'value'
    assert environment.to_environ() == {'TMT_TEST': 'value'}

    assert environment.setdefault(ENV_TMT_TEST, EnvVarValue('other')) == 'value'

    del environment[ENV_TMT_TEST]
    assert not environment
