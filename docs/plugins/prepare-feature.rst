.. include:: prepare-feature-header.inc.rst



profile
^^^^^^^



.. warning::

    Please, be aware that the documentation below is a work in progress. We are
    working on fixing it, adding missing bits and generally making it better.
    Also, it was originally used for command line help only, therefore the
    formatting is often suboptimal.

Prepare guest setup with a guest profile.

.. note::

    Guest profiles are being developed, once there is an agreed upon
    text we could steal^Wborrow^Wreuse, we shall add it to this
    docstring.

Guest profiles represent a particular setup of guest environment as
defined by a CI system or service. They are implemented as Ansible
roles, and packaged as Ansible collections. The CI systems use
profiles to set up guests before testing, and users may use the same
profiles to establish the same environment locally when developing
tests or reprodcing issues.

Apply a profile to the guest:

.. code-block:: yaml

    prepare:
        how: feature
        profile: testing_farm.fedora_ci

.. code-block:: shell

    prepare --how feature --profile testing_farm.fedora_ci





profile: ``NAME``
    Apply guest profile.

    Default: *not set*


----





epel
^^^^



.. warning::

    Please, be aware that the documentation below is a work in progress. We are
    working on fixing it, adding missing bits and generally making it better.
    Also, it was originally used for command line help only, therefore the
    formatting is often suboptimal.

Control Extra Packages for Enterprise Linux (EPEL) repository.

`EPEL`__ is an initiative within the Fedora Project to provide high
quality additional packages for CentOS Stream and Red Hat Enterprise
Linux (RHEL).

Enable or disable EPEL repository on the guest:

.. code-block:: yaml

    prepare:
        how: feature
        epel: enabled

.. code-block:: shell

    prepare --how feature --epel enabled

__ https://docs.fedoraproject.org/en-US/epel/





epel: ``enabled|disabled``
    Whether EPEL repository should be installed & enabled or disabled.

    Default: *not set*


----





fips
^^^^



.. warning::

    Please, be aware that the documentation below is a work in progress. We are
    working on fixing it, adding missing bits and generally making it better.
    Also, it was originally used for command line help only, therefore the
    formatting is often suboptimal.






fips: ``enabled``
    Whether FIPS mode should be enabled

    Default: *not set*
