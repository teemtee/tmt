import re

import tmt
import tmt.utils

logger = tmt.Logger.create()
tree = tmt.Tree(logger=logger, path='data')

# Try to find out what git thinks about the origin of the repository.
# This should deal with custom SSH `Host` config one might have for
# Github.
try:
    output = tmt.utils.Command('git', 'config', '--get', 'remote.origin.url').run(
        cwd=None,
        logger=logger)

    base_url = output.stdout.strip().replace('.git', '')

except tmt.utils.RunError:
    base_url = r'https://github.com/.*/tmt'

prefix = rf'{base_url}/tree/.*/tests/core/web-link/data/'


def test_stories():
    url = tree.stories(names=['/story'])[0].web_link()
    assert re.match(prefix + 'story.fmf', url)


def test_plans():
    url = tree.plans(names=['/plan'])[0].web_link()
    assert re.match(prefix + 'plan.fmf', url)


def test_tests():
    url = tree.tests(names=['/test'])[0].web_link()
    assert re.match(prefix + 'test.fmf', url)
