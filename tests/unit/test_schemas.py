import itertools
import os
import textwrap

import fmf
import pytest

import tmt
import tmt.log
import tmt.utils

PATH = os.path.dirname(os.path.realpath(__file__))
ROOTDIR = os.path.join(PATH, "../..")

LOGGER = tmt.log.Logger.create(verbose=0, debug=0, quiet=False)

# This is what `Tree.{tests,plans,stories}`` do internally, but after getting
# all nodes, these methods would construct tmt objects representing found
# nodes. That is *not* what we want, because the act of instantiating a `Plan``
# object, for example, would affect content of the corresponding node, e.g.
# `Plan` class would add some missing keys, using predefined default values.
#
# We want raw nodes here, therefore we need to get our hands on them before
# `Tree` modifies them - use the underlying fmf tree's `prune()` method, and
# use the right keys to filter out nodes we're interested in (the same `Tree`
# uses).


def _iter_nodes(tree, keys):
    for node in tree.tree.prune(keys=keys):
        yield tree, node


def _iter_trees():
    yield tmt.Tree(logger=LOGGER, path=ROOTDIR)

    # Ad hoc construction, but here me out: there are small, custom-tailored fmf trees
    # to serve various tests. These are invisible to the top-level tree. Lucky us though,
    # they are still fmf trees, therefore we can look for .fmf directories under tests/.
    #
    # TODO: disabled on purpose - when enabled, there's plenty of failed tests, including
    # those that are expected to be broken as they are used to verify `tmt lint` or similar
    # features. First we need to find a way how to get those ignored by this generator.
    # But the code below works, like a charm, and we will need to cover more trees than
    # just the root one, so leaving the code here but disabled.
    if False:
        for dirpath, dirnames, _ in os.walk(os.path.join(ROOTDIR, 'tests')):
            if '.fmf' in dirnames:
                yield tmt.Tree(path=dirpath)


def _iter_tests_in_tree(tree):
    yield from _iter_nodes(tree, ['test'])


def _iter_plans_in_tree(tree):
    yield from _iter_nodes(tree, ['execute'])


def _iter_stories_in_tree(tree):
    yield from _iter_nodes(tree, ['story'])


TESTS = itertools.chain.from_iterable(_iter_tests_in_tree(tree) for tree in _iter_trees())
PLANS = itertools.chain.from_iterable(_iter_plans_in_tree(tree) for tree in _iter_trees())
STORIES = itertools.chain.from_iterable(_iter_stories_in_tree(tree) for tree in _iter_trees())


def validate_node(tree, node, schema, label, name):
    errors = tmt.utils.validate_fmf_node(node, schema, LOGGER)

    if errors:
        print(f"""A node in tree loaded from {_tree_path(tree)!s} failed validation
""")

        for error, message in errors:
            print(f"""* {message}

Detailed validation error:

{textwrap.indent(str(error), '  ')}
""")

        pytest.fail(f"{label} {name} fails validation")


def _tree_path(tree):
    return os.path.relpath(os.path.abspath(tree._path))


def extract_testcase_id(arg):
    if isinstance(arg, tmt.Tree):
        return _tree_path(arg)

    return arg.name


@pytest.mark.parametrize(('tree', 'test'), TESTS, ids=extract_testcase_id)
def test_tests_schema(tree, test):
    validate_node(tree, test, 'test.yaml', 'Test', test.name)


@pytest.mark.parametrize(('tree', 'story'), STORIES, ids=extract_testcase_id)
def test_stories_schema(tree, story):
    validate_node(tree, story, 'story.yaml', 'Story', story.name)


@pytest.mark.parametrize(('tree', 'plan'), PLANS, ids=extract_testcase_id)
def test_plans_schema(tree, plan):
    validate_node(tree, plan, 'plan.yaml', 'Plan', plan.name)


#
# Exercise the HW requirement schema with some interesting examples
#
@pytest.mark.parametrize(
    'hw',
    [
        """
            ---

            #arch: x86_64
            boot:
                method: bios
            compatible:
                distro:
                    - rhel-7
                    - rhel-8
            cpu:
                sockets: 1
                cores: 2
                threads: 8
                cores-per-socket: 2
                threads-per-core: 4
                processors: 8
                model: 62
                model-name: Haswell
                family: 6
                family-name: Skylake
            disk:
                - size: 40 GiB
                - size: 120 GiB
            hostname: foo.dot.com
            memory: 8 GiB
            network:
                - type: eth
                - type: eth
            system:
                vendor: HPE
                model: ProLiant DL385 Gen10
                numa-nodes: ">= 2"
            tpm:
                version: "2.0"
            virtualization:
                is-supported: true
                is-virtualized: false
                hypervisor: xen
            """,
        """
            ---

            and:
              #- arch: x86_64
              - cpu:
                  model-name: foo
              - memory: 8 GiB
              - or:
                  - virtualization:
                      is-supported: true
                  - virtualization:
                      is-supported: false
            """
        ],
    ids=[
        'all-requirements',
        'conditions'
        ]
    )
def test_hw_schema_examples(hw: str, request) -> None:
    tree = tmt.Tree(logger=LOGGER)

    # Our hardware schema is supposed to be referenced from provision plugin schemas.
    # Instead of cutting it out, we can use a provision plugin schema & prepare the
    # fmf node correctly, to pretend it comes from `provision` step. The only required
    # field is usually `how`.
    node = fmf.Tree(
        {
            'how': 'artemis',
            'hardware': tmt.utils.yaml_to_dict(textwrap.dedent(hw), yaml_type='safe')
            }
        )

    validate_node(
        tree,
        node,
        os.path.join('provision', 'artemis.yaml'),
        'HW requirements',
        request.node.callspec.id
        )


#
# Exercise the KS requirement schema with some real examples
#
@pytest.mark.parametrize(
    'ks',
    [
        """
            ---

            pre-install: |
                %pre --log=/tmp/kickstart_pre.log
                echo "Pre-install ks script"
                %end
            post-install: |
                %post --nochroot
                umount --recursive /mnt/sysimage
                %end
            script: |
                lang en_US.UTF-8
                keyboard us
                part /boot --fstype="xfs" --size=200
                part swap --fstype="swap" --size=4096
                part / --fstype="xfs" --size=10000 --grow
            metadata: |
                "no-autopart harness=restraint"
            kernel-options: "ksdevice=eth1"
            kernel-options-post: "quiet"
            """],
    ids=[
        'all-properties',
        ]
    )
def test_ks_schema_examples(ks: str, request) -> None:
    tree = tmt.Tree(logger=LOGGER)

    # Our kickstart schema is supposed to be referenced from provision plugin schemas.
    # Instead of cutting it out, we can use a provision plugin schema & prepare the
    # fmf node correctly, to pretend it comes from `provision` step. The only required
    # field is usually `how`.
    node = fmf.Tree(
        {
            'how': 'artemis',
            'kickstart': tmt.utils.yaml_to_dict(textwrap.dedent(ks), yaml_type='safe')
            }
        )

    validate_node(
        tree,
        node,
        os.path.join('provision', 'artemis.yaml'),
        'Kickstart requirements',
        request.node.callspec.id
        )


def test_watchdog_specification() -> None:
    tree = tmt.Tree(logger=LOGGER)

    # Our user defined watchdog timeout values for artemis are supposed to be referenced
    # from provision plugin schemas. Instead of cutting it out, we can use a provision
    # plugin schema & prepare the fmf node correctly, to pretend it comes from `provision` step.
    # The only required field is usually `how`.
    node = fmf.Tree(
        {
            'how': 'artemis',
            'watchdog-period-delay': 10,
            'watchdog-dispatch-delay': 42,
            }
        )

    validate_node(
        tree,
        node,
        os.path.join('provision', 'artemis.yaml'),
        'Watchdog specification',
        'both-wd-options'
        )
