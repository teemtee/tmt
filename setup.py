#!/usr/bin/env python

import re
from typing import Dict, List

from setuptools import setup

# Parse version from the spec file
with open('tmt.spec', encoding='utf-8') as specfile:
    lines = "\n".join(line.rstrip() for line in specfile)

    match = re.search('Version: (.+)', lines)
    assert match is not None, "Could not find 'Version:' in tmt.spec"
    version = match.group(1).rstrip()

# acceptable version schema: major.minor[.patch][sub]
__version__ = version
__pkg__ = 'tmt'
__pkgdata__ = {
    'tmt': [
        'py.typed',
        'export/templates/*',
        'schemas/*.yaml',
        'schemas/*/*.yaml',
        'steps/execute/scripts/*',
        'steps/report/html/*',
        'steps/provision/mrack/*',
        ]
    }
__pkgdir__: Dict[str, str] = {}
__pkgs__ = [
    'tmt',
    'tmt/checks',
    'tmt/export',
    'tmt/frameworks',
    'tmt/libraries',
    'tmt/plugins',
    'tmt/steps',
    'tmt/steps/discover',
    'tmt/steps/provision',
    'tmt/steps/prepare',
    'tmt/steps/execute',
    'tmt/steps/report',
    'tmt/steps/finish',
    ]
__provides__ = ['tmt']
__desc__ = 'Test Management Tool'
__scripts__ = ['bin/tmt']

# Prepare install requires and extra requires
install_requires = [
    'fmf>=1.2.1',
    'click!=8.1.4',
    # 'pint>=0.22',
    'pint',
    'requests',
    'urllib3',
    'ruamel.yaml',
    'jinja2',
    'setuptools',
    ]

extras_require = {
    'docs': [
        'sphinx>=3',
        'sphinx-rtd-theme==1.3.0rc1'],
    'tests': [
        'flake8',
        'pytest',
        'python-coveralls',
        'requre',
        'pre-commit',
        'mypy',
        "typing-extensions>=3.7.4.3; python_version < '3.10'",
        'yq==3.1.1'  # frozen to be able to install on el8
        ],
    'provision': [
        'testcloud>=0.9.2',
        'mrack>=1.12.1',
        ],
    'convert': [
        'nitrate',
        'markdown',
        'python-bugzilla',
        'html2text'],
    'report-junit': ['junit_xml'],
    'report-polarion': ['junit_xml', 'pylero'],
    'export-polarion': ['pylero'],
    }
extras_require['all'] = [
    dependency
    for extra in extras_require.values()
    for dependency in extra]

pip_src = 'https://pypi.python.org/packages/source'
__deplinks__: List[str] = []

# README is in the parent directory
readme = 'README.rst'
with open(readme, encoding='utf-8') as _file:
    readme = _file.read()

github = 'https://github.com/teemtee/tmt'
download_url = f'{github}/archive/main.zip'

setup(
    url=github,
    license='MIT',
    author='Petr Splichal',
    author_email='psplicha@redhat.com',
    maintainer='Petr Splichal',
    maintainer_email='psplicha@redhat.com',
    download_url=download_url,
    long_description=readme,
    data_files=[],
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12'
        'Topic :: Utilities',
        ],
    keywords=['metadata', 'testing'],
    dependency_links=__deplinks__,
    description=__desc__,
    install_requires=install_requires,
    extras_require=extras_require,
    name=__pkg__,
    package_data=__pkgdata__,
    package_dir=__pkgdir__,
    packages=__pkgs__,
    provides=__provides__,
    scripts=__scripts__,
    version=__version__
    )
