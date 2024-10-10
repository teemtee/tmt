.. _testing-farm:

Testing Farm
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
