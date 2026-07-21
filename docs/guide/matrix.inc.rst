.. _matrix:

Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When you need to run the same tests across multiple configurations,
the ``matrix`` key in a plan lets you define variables and their
values, and automatically expand them into separate test runs. Instead of
duplicating plans that differ only in a few parameters:

.. code-block:: yaml

    # Without matrix: four nearly identical plans

    /plans/test-debug-fedora:
        summary: Run tests in debug mode on Fedora
        provision:
            how: container
            image: fedora
        environment:
            MODE: debug
        discover:
            how: fmf
        execute:
            how: tmt

    /plans/test-debug-ubuntu:
        summary: Run tests in debug mode on Ubuntu
        provision:
            how: container
            image: ubuntu
        environment:
            MODE: debug
        discover:
            how: fmf
        execute:
            how: tmt

    /plans/test-release-fedora:
        summary: Run tests in release mode on Fedora
        provision:
            how: container
            image: fedora
        environment:
            MODE: release
        discover:
            how: fmf
        execute:
            how: tmt

    /plans/test-release-ubuntu:
        summary: Run tests in release mode on Ubuntu
        provision:
            how: container
            image: ubuntu
        environment:
            MODE: release
        discover:
            how: fmf
        execute:
            how: tmt

You can write a single plan with a ``matrix``:

.. code-block:: yaml

    summary: Run tests across modes and distros
    matrix:
        mode: [debug, release]
        distro: [fedora, ubuntu]
    provision:
        how: container
        image: $TMT_MATRIX_DISTRO
    discover:
        how: fmf
    execute:
        how: tmt

This produces four derived plans named after their combination
values:

* ``/plans/test.debug-fedora``
* ``/plans/test.debug-ubuntu``
* ``/plans/test.release-fedora``
* ``/plans/test.release-ubuntu``

Each plan has the matrix values available as environment variables
``TMT_MATRIX_MODE`` and ``TMT_MATRIX_DISTRO``. The
``$TMT_MATRIX_DISTRO`` reference in the provision step is expanded
to the actual value for each combination. Test scripts can also
read these variables directly, for example ``$TMT_MATRIX_MODE`` in
a shell test.

Filtering from the Command Line
------------------------------------------------------------------

Use ``--matrix-filter`` to run only specific combinations without
modifying the plan:

.. code-block:: shell

    # Run only debug combinations
    tmt run --matrix-filter mode=debug

    # Run a single specific combination
    tmt run --matrix-filter mode=debug --matrix-filter distro=fedora

Multiple filters are combined with AND logic, so all specified
filters must match for a combination to run.
