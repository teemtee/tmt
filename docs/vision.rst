.. _vision:

======================
    Vision
======================

This page captures what tmt is, the original motivation and main
ideas behind the tool, which features belong to its scope and
which do not.


Why
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is always good to start with the why.

Testing was not a joyful task. Test metadata were stored in an
ugly format in `Makefiles`_. Execution leaned heavily on a single
backend such as Beaker. Tests were tightly coupled to the internal
infrastructure and could not be easily open sourced. Additional
test metadata lived in one test case management system, then in
another, then there was a plan for yet another one... Tests were
run in different ways from project to project, enabled in CI in
different ways, and when something broke, reproducing and
debugging the failure locally was hard.

The result was duplicated effort, little sharing between projects
and a fresh learning curve each time you moved somewhere new. The
tmt tool and specification grew out of the wish to replace this
patchwork with a single, consistent way to create, run and debug
tests, one that behaves the same on your laptop as it does in CI,
all the way from upstream projects down to the released
distributions.


Concept
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The essential tmt features, built on the :ref:`cornerstones`, are:

* concise config ... consistent from upstream to downstream
* plain text, versioned under git ... no accounts necessary
* yaml with inheritance & hierarchy ... preventing duplication
* liberated tests ... independent of internal infrastructure
* distributed metadata design ... enabling easy test sharing

We aim to provide a stable, reliable, user-friendly and efficient
tool.


Mission
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

tmt is a tool for managing tests and safely executing them across
different environments such as local, container, virtual or CI. It
covers test creation, discovery, organization, execution and
interactive debugging, together with results reporting and
coverage tracking for features and requirements.

A single, consistent config can be used to enable tests in the
very same way from upstream projects to downstream distributions.
Metadata are stored and shared via git using the `Flexible
Metadata Format`_, kept close to the code and easy to reuse across
projects.

It is a layer that connects the dots between the many tools and
services involved in testing, from guest provisioning and setup to
result reporting. Rather than trying to replace them, it reuses
and integrates them, helping them play nicely together so that
developers and testers can work with tests easily and efficiently.


In Scope
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following areas are the core concern of tmt:

* Test metadata, hierarchical, inheritable and git-native, using
  fmf (core, tests, plans and stories), linking features to code,
  tests and docs
* Test creation, discovery and organization across local and
  remote repositories.
* A complete, end-to-end workflow covering the discover,
  provision, prepare, execute, finish, report and cleanup steps.
* An interactive mode which provisions an environment and lets you
  experiment, develop and debug tests right there
* A provisioner-agnostic environment abstraction together with a
  generic hardware requirements language.
* Test framework-agnostic execution, running tests of any
  framework as a backend.
* Context-aware behavior, metadata linting and result reporting
  through plugins.


Out of Scope
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

tmt deliberately integrates with existing tools rather than
replacing them. It is **not**:

* a :term:`test framework`, tmt does not define how individual
  tests are written. There is no single way to test and every
  technology might require a different framework to be used based
  on the test author's needs. tmt wraps around frameworks and
  executes tests of any of them.
* a CI, gating or build system, tmt runs inside them
* a service, tmt is a command-line tool and a library
* a provisioning or virtualization tool, but it uses libvirt,
  Podman and cloud APIs through plugins
* an infrastructure-management tool, tmt uses Ansible and supports
  custom shell scripts for guest preparation
* a test-result management system, but tmt integrates with several
  of them
* tied to any single programming language, framework, operating
  system, cloud or runtime, and it is also not limited to the
  Fedora/RHEL ecosystem
* a monolith, tmt is a plugin architecture where you use only what
  you need


Guiding Principles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There are two main guiding principles for the decision of whether
a certain functionality belongs to tmt or not:

Integrate rather than duplicate
    Prefer reusing an existing, mature solution over building the
    same capability again inside tmt.

Plugin over core
    Prefer delivering functionality as a plugin, and extend the
    core only as much as enabling that plugin requires.

The principles above become actionable through a short set of
questions. When a new feature or request is considered, work
through them in order. First decide whether it belongs in tmt
at all:

Is there an existing solution we can integrate or extend instead?
    If a mature tool already does it, prefer integration over
    reimplementation.

Can't we do this outside of tmt?
    If users can already achieve it with existing tools or a thin
    wrapper, it likely does not belong in tmt.

Is it hard to achieve outside of tmt?
    The stronger the case that it is genuinely difficult without the
    orchestration and metadata layer, the stronger the case for
    including it.

Then, if it fits, decide how it should live in tmt:

Could it be implemented as a plugin?
    Prefer delivering the feature as a plugin and identify the
    minimal core support it needs, such as interfaces, hooks or
    shared utilities.

Does it have to be implemented in the core?
    Add to the core only what cannot live in a plugin, such as shared
    functionality several plugins build upon, and keep that addition
    as small as possible.

In short: integrate before building, build outside the core before
building inside it, and add to the core only what a plugin genuinely
needs.

.. _Makefiles: https://github.com/teemtee/tmt/blob/main/examples/convert/Makefile#L29-L48
.. _Flexible Metadata Format: https://fmf.readthedocs.io/
