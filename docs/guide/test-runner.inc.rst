.. _test-runner:

Test Runner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We use the term **test runner** for the system on which the ``tmt
run`` command is executed. This may be a user system, such as a
laptop used for test development, or a testing service which takes
care of the execution. This section covers some important details
about common test runners.


.. _user-system:

User System
------------------------------------------------------------------

For developing tests users install the ``tmt`` package on their
system so that they can easily create new tests or quickly run
locally modified code to debug test failures.

By default the :ref:`/plugins/provision/virtual.testcloud` plugin
is used to provision a full virtual machine so that tests can use
the full features of a virtualized guest, safely without affecting
user system. If the full virtualization is not needed you can
consider using the :ref:`/plugins/provision/container` plugin and
execute test faster in a container. To execute tests directly on
the test runner use the :ref:`/plugins/provision/local` provision
plugin. This can be much faster but also dangerous, be sure that
you trust the project before executing tests on your system. See
also the :ref:`/stories/features/feeling-safe` section.


.. _testing-farm:

Testing Farm
------------------------------------------------------------------

The ``tmt`` tool is being developed in close collaboration with
the `Testing Farm`__ project, a reliable and scalable Testing
System as a Service which allows to easily execute tests across
various environments.

Scheduling tests can be done through a public `API`__ or using the
`testing-farm`__ command line tool. After onboarding to the
project, scheduling a test job is as easy as entering the git
repository with tests and selecting the desired compose:

.. code-block:: shell

   testing-farm request --compose Fedora-latest

Check the Testing Farm documentation for the `onboarding`__
instructions, list of available `composes`__ and other details.
Note that when executing tests in the Testing Farm, `selected
ansible collections`__ are available on the test runner and can be
used in user playbooks.

__ https://docs.testing-farm.io/
__ https://api.testing-farm.io/redoc
__ https://docs.testing-farm.io/Testing%20Farm/0.1/cli.html
__ https://docs.testing-farm.io/Testing%20Farm/0.1/onboarding.html
__ https://docs.testing-farm.io/Testing%20Farm/0.1/test-environment.html#_composes
__ https://docs.testing-farm.io/Testing%20Farm/0.1/test-runner.html#_supported_ansible_collections

.. include:: guide/test-runner-guest-compatibility-matrix.inc.rst
