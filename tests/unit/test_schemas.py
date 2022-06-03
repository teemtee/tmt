import os
import subprocess

import pytest
from ruamel.yaml import YAML

import tmt

PATH = os.path.dirname(os.path.realpath(__file__))
SCHEMADIR = os.path.join(PATH, "../../tmt/schemas")

# make sure tmt tree is initialized, required when tests run during rpmbuild
tmt.base.Tree.init('.', 'empty', False)


@pytest.fixture
def tests_schema():
    # TODO: tmt package shall provide a helper function
    # for "load schemas for test/plan/story"
    schema_file = os.path.join(SCHEMADIR, 'tests.yaml')
    return YAML(typ="safe").load(open(schema_file, encoding="utf-8"))


@pytest.fixture
def stories_schema():
    # TODO: tmt package shall provide a helper function
    # for "load schemas for test/plan/story"
    schema_file = os.path.join(SCHEMADIR, 'stories.yaml')
    return YAML(typ="safe").load(open(schema_file, encoding="utf-8"))


@pytest.fixture
def plans_schema():
    # TODO: tmt package shall provide a helper function
    # for "load schemas for test/plan/story"
    schema_file = os.path.join(SCHEMADIR, 'plans.yaml')
    return YAML(typ="safe").load(open(schema_file, encoding="utf-8"))


@pytest.fixture
def schema_store():
    # TODO: tmt package shall provide a helper function
    # for "load schemas for test/plan/story"
    store = {}

    for schema_name in ('common', 'core'):
        schema_file = os.path.join(SCHEMADIR, f'{schema_name}.yaml')
        schema = YAML(
            typ="safe").load(
            open(
                schema_file,
                encoding="utf-8"))
        store[schema['$id']] = schema

    return store


@pytest.fixture(params=tmt.Tree('.').tests())
def test_validation_result(request, schema_store, tests_schema):
    node = request.param.node
    return node.name, node.validate(tests_schema, schema_store)


@pytest.fixture(params=tmt.Tree('.').stories())
def story_validation_result(request, schema_store, stories_schema):
    node = request.param.node
    return node.name, node.validate(stories_schema, schema_store)


@pytest.fixture(params=tmt.Tree('.').plans())
def plan_validation_result(request, schema_store, plans_schema):
    node = request.param.node
    return node.name, node.validate(plans_schema, schema_store)


def test_tests_schema(test_validation_result):
    name, result = test_validation_result
    if not result.result:
        for error in result.errors:
            print(error)

    assert result.result, f'Test {name} fails validation'


def test_stories_schema(story_validation_result):
    name, result = story_validation_result
    if not result.result:
        for error in result.errors:
            print(error)

    assert result.result, f'Story {name} fails validation'


def test_plans_schema(plan_validation_result):
    name, result = plan_validation_result
    if not result.result:
        for error in result.errors:
            print(error)

    assert result.result, f'Plan {name} fails validation'
