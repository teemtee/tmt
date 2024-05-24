.. _plugin_introduction:

===========================
    Plugin Introduction
===========================

Let's have a look at plugins. Each of the six steps defined by
:ref:`/spec/plans` supports multiple methods. These methods are
implemented by plugins which are dynamically loaded from the
standard location under ``tmt/steps`` , from all directories
provided in the ``TMT_PLUGINS`` environment variable and from
``tmt.plugin`` entry point.

.. versionchanged:: 1.35
   ``warnings.deprecated`` is used to advertise deprecated APIs.
   Consider adding a static type checker (e.g. ``mypy``) in your
   plugin's CI using the ``main`` branch of ``tmt``.

.. versionadded:: 1.62
   You can use ``tmt.resources`` entry point to inject resource
   files to be used for tmt, e.g. schemas or templates. See
   :ref:`additional-resources` for more details.


Inheritance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The plugin is implemented by a class which inherits from the
corresponding step class, for example ``ProvisionPodman`` inherits
from the ``ProvisionPlugin`` class. See the :ref:`classes` page
for more details about the class structure. The plugin class
defines a couple of essential methods:

options()
    command line options specific for given plugin

wake()
    additional plugin data processing after the wake-up

show()
    give a concise overview of the step configuration

go()
    the main implementation of the plugin functionality

There may be additional required methods which need to be
implemented. See individual plugin examples for details.


Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Example plugin skeletons are located in the `examples/plugins`__
directory. Get some inspiration for writing plugins there. There
is a lot of comments and you can use the examples as a skeleton
for your new plugin.

The ``discover`` plugin example demonstrates a simple plugin
functionality defining an additional ``tests()`` method which
returns a list of discovered tests.

The ``provision`` step example is more complex and consists of two
classes. In addition to the provisioning part itself it also
implements the ``GuestExample`` class which inherits from
``Guest`` and overloads its methods to handle special guest
features which cannot be covered by generic ssh implementation of
the ``Guest`` class.

__ https://github.com/teemtee/tmt/tree/main/examples/plugins

.. _additional-resources:

Additional resource files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In order to make resource files available to the base ``tmt``
execution, you need to point a ``tmt.resources`` entry point to the
root python package where the resource files are located from, e.g.
with in the ``examples/plugins``:

.. code-block:: toml
   :caption: pyproject.toml
   :emphasize-lines: 5,6

   [project.entry-points."tmt.plugin"]
   ProvisionExample = "example.provision:ProvisionExample"
   DiscoverExample = "example.discover:DiscoverExample"

   [project.entry-points."tmt.resources"]
   ResourcesExample = "example"

you can, for example, add a json schema file for the plugins
implemented above by including the schema files under a ``schemas``
folder:

.. code-block:: shell

   $ tree ./example
   ./example
   ├── __init__.py
   ├── discover.py
   ├── provision.py
   └── schemas
       ├── discover
       │   └── example.yaml
       └── provision
           └── example.yaml

.. note::

   Both the entry-point entries as well as any resource file
   under the ``tmt.resources`` path **must** have unique names.
   Consider namespacing all relevant entries with the name of the
   project or an unambiguous derivative of it.
