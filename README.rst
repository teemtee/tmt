
==================================================================
                    tmt - Test Management Tool
==================================================================

|docs| |matrix| |fedora-pkg| |copr-build| |pypi-version| |python-versions| |license|

The ``tmt`` tool provides a user-friendly way to work with tests.
You can comfortably create new tests, safely and easily run tests
across different environments, review test results, debug test
code and enable tests in the CI using a consistent and concise
config.

The python module and command-line tool implement the Metadata
Specification which allows storing all needed test execution data
directly within a git repository. Together with the possibility to
reference remote repositories, it makes it easy to share test
coverage across projects and distros.

The Flexible Metadata Format ``fmf`` is used to store data in both
human and machine readable way close to the source code. Thanks to
inheritance and elasticity metadata are organized in the structure
efficiently, preventing unnecessary duplication.

See the https://tmt.readthedocs.io web for detailed documentation.

.. |docs| image:: https://img.shields.io/badge/Read%20the%20Docs-8CA1AF?logo=readthedocs&logoColor=fff
    :target: https://tmt.readthedocs.io/
    :alt: Documentation

.. |matrix| image:: https://img.shields.io/badge/Matrix-000?logo=matrix&logoColor=fff
    :target: https://matrix.to/#/#tmt:fedoraproject.org
    :alt: Matrix chat

.. |fedora-pkg| image:: https://img.shields.io/fedora/v/tmt?logo=fedora&logoColor=fff&color=fff&labelColor=51a2da
    :target: https://src.fedoraproject.org/rpms/tmt
    :alt: Fedora package

.. |copr-build| image:: https://img.shields.io/badge/dynamic/json?color=blue&label=Copr&query=builds.latest.state&url=https%3A%2F%2Fcopr.fedorainfracloud.org%2Fapi_3%2Fpackage%3Fownername%3D%40teemtee%26projectname%3Dlatest%26packagename%3Dtmt%26with_latest_build%3DTrue
    :target: https://copr.fedorainfracloud.org/coprs/g/teemtee/stable/
    :alt: Copr build status

.. |pypi-version| image:: https://img.shields.io/badge/PyPI-3775A9?logo=pypi&logoColor=fff
    :target: https://pypi.org/project/tmt/
    :alt: PyPI

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/tmt
    :target: https://pypi.org/project/tmt/
    :alt: Python versions

.. |license| image:: https://img.shields.io/badge/license-MIT-blue.svg
    :target: https://opensource.org/licenses/MIT
    :alt: MIT License
