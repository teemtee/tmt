import pytest

from tmt.convert import relevancy_to_adjust
from tmt.utils import ConvertError


@pytest.fixture()
def mini(root_logger):
    """ Minimal example """
    return relevancy_to_adjust("distro = fedora: False", root_logger)


@pytest.fixture()
def full(root_logger):
    """ Full example """
    return relevancy_to_adjust("""
    # feature has been added in Fedora 33
    distro < fedora-33: False

    # using logical operators
    component = firefox && arch = ppc64: False

    arch = s390x: PHASES=novalgrind # modify environment

    # try special operators
    collection contains httpd24 && fips defined: False
    """.replace('    ', ''), root_logger)


def check(condition, expected, logger):
    """ Check condition against expected """
    adjusted = relevancy_to_adjust(f"{condition}: False", logger)[0]['when']
    assert adjusted == expected


# Valid rules

def test_empty(root_logger):
    """ Empty relevancy """
    assert relevancy_to_adjust('', root_logger) == []


def test_comments(full):
    """ Extract comments """
    assert full[0]['because'] == 'feature has been added in Fedora 33'
    assert full[1]['because'] == 'using logical operators'
    assert full[2]['because'] == 'modify environment'


def test_disable(mini, full):
    """ Disable test """
    assert mini[0]['enabled'] is False
    assert full[0]['enabled'] is False
    assert full[1]['enabled'] is False


def test_environment(full):
    """ Modify environment """
    assert full[2]['environment'] == {'PHASES': 'novalgrind'}


def test_continue(mini):
    """ Explicit continue """
    assert mini[0]['continue'] is False


def test_condition(mini, full):
    """ Expressions conversion """
    assert mini[0]['when'] == 'distro == fedora'
    assert full[0]['when'] == 'distro < fedora-33'
    assert full[1]['when'] == 'component == firefox and arch == ppc64'
    assert full[2]['when'] == 'arch == s390x'
    assert full[3]['when'] == 'collection == httpd24 and fips is defined'


def test_operators_basic(root_logger):
    """ Basic operators unchanged """
    check('component = python', 'component == python', root_logger)
    check('component == python', 'component == python', root_logger)
    check('arch == s390x', 'arch == s390x', root_logger)
    check('arch != s390x', 'arch != s390x', root_logger)


def test_operators_distro_name(root_logger):
    """ Check distro name """
    check('distro = fedora', 'distro == fedora', root_logger)
    check('distro == fedora', 'distro == fedora', root_logger)
    check('distro != fedora', 'distro != fedora', root_logger)


def test_operators_distro_major(root_logger):
    """ Check distro major version """
    check('distro < fedora-33', 'distro < fedora-33', root_logger)
    check('distro > fedora-33', 'distro > fedora-33', root_logger)
    check('distro <= fedora-33', 'distro <= fedora-33', root_logger)
    check('distro >= fedora-33', 'distro >= fedora-33', root_logger)


def test_operators_distro_minor(root_logger):
    """ Check distro minor version """
    check('distro = centos-8.3', 'distro ~= centos-8.3', root_logger)
    check('distro == centos-8.3', 'distro ~= centos-8.3', root_logger)
    check('distro != centos-8.3', 'distro ~!= centos-8.3', root_logger)
    check('distro < centos-8.3', 'distro ~< centos-8.3', root_logger)
    check('distro > centos-8.3', 'distro ~> centos-8.3', root_logger)
    check('distro <= centos-8.3', 'distro ~<= centos-8.3', root_logger)
    check('distro >= centos-8.3', 'distro ~>= centos-8.3', root_logger)


def test_operators_product(root_logger):
    """ Special handling for product """
    # rhscl
    check('product = rhscl', 'product == rhscl', root_logger)
    check('product == rhscl', 'product == rhscl', root_logger)
    check('product != rhscl', 'product != rhscl', root_logger)
    # rhscl-3
    check('product < rhscl-3', 'product < rhscl-3', root_logger)
    check('product > rhscl-3', 'product > rhscl-3', root_logger)
    check('product <= rhscl-3', 'product <= rhscl-3', root_logger)
    check('product >= rhscl-3', 'product >= rhscl-3', root_logger)
    # rhscl-3.3
    check('product < rhscl-3.3', 'product ~< rhscl-3.3', root_logger)
    check('product > rhscl-3.3', 'product ~> rhscl-3.3', root_logger)
    check('product <= rhscl-3.3', 'product ~<= rhscl-3.3', root_logger)
    check('product >= rhscl-3.3', 'product ~>= rhscl-3.3', root_logger)


def test_operators_special(root_logger):
    """ Check 'defined' and 'contains' """
    check('fips defined', 'fips is defined', root_logger)
    check('fips !defined', 'fips is not defined', root_logger)
    check('collection contains http24', 'collection == http24', root_logger)
    check('collection !contains http24', 'collection != http24', root_logger)


def test_not_equal_comma_separated(root_logger):
    """ Special handling for comma-separated values with != """
    check(
        'distro != centos-7, centos-8',
        'distro != centos-7 and distro != centos-8',
        root_logger)


# Invalid rules

def test_invalid_rule(root_logger):
    """ Invalid relevancy rule """
    with pytest.raises(ConvertError, match='Invalid.*rule'):
        relevancy_to_adjust("weird", root_logger)


def test_invalid_decision(root_logger):
    """ Invalid relevancy decision """
    with pytest.raises(ConvertError, match='Invalid.*decision'):
        relevancy_to_adjust("distro < fedora-33: weird", root_logger)


def test_invalid_expression(root_logger):
    """ Invalid relevancy expression """
    with pytest.raises(ConvertError, match='Invalid.*expression'):
        relevancy_to_adjust("distro * fedora-33: False", root_logger)


def test_invalid_operator(root_logger):
    """ Invalid relevancy operator """
    with pytest.raises(ConvertError, match='Invalid.*operator'):
        relevancy_to_adjust("distro <> fedora-33: False", root_logger)
