.. _vision:

======================
    Vision
======================

This page captures what ``tmt`` is, the main ideas behind the
tool, which features belong to its scope and how it compares to
other tools.


Mission
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``tmt`` is a tool for managing tests and safely executing them
across different environments such as local, container, virtual or
CI. It covers test creation, discovery, organization, execution
and interactive debugging, together with results reporting and
coverage tracking for features and requirements.

A single, consistent config can be used to enable tests in the
very same way from upstream projects to downstream distributions.
Metadata is stored and shared via git using the Flexible Metadata
Format, kept close to the code and easy to reuse across projects.

It is a layer that connects the dots between the many tools and
services involved in testing, from guest provisioning and setup to
result reporting. Rather than trying to replace them, it reuses
and integrates them, helping them play nicely together so that
developers and testers can work with tests easily and efficiently.


Concept
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The concept in just a few words:

* consistent, concise config
* plain text, versioned under git
* yaml with inheritance & hierarchy
* distributed design enabling test sharing

We aim to provide a stable, reliable, user-friendly and efficient
tool.


In Scope
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following areas are the core concern of ``tmt``:

* Test metadata, hierarchical, inheritable and git-native, using
  fmf (core, tests, plans and stories).
* Test creation, discovery and organization across local and
  remote repositories.
* A complete, end-to-end workflow covering the discover,
  provision, prepare, execute, report, finish and cleanup steps.
* A provisioner-agnostic environment abstraction together with a
  generic hardware requirements language.
* Framework-agnostic execution, running tests of any framework as
  a backend.
* Context-aware behavior, interactive iteration, metadata linting
  and result reporting through plugins.


Out of Scope
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``tmt`` deliberately integrates with existing tools rather than
replacing them. It is **not**:

* a test framework, it does not define how individual tests are
  written. There is no single way to test, for example, a
  graphical application, so writing the test itself is up to the
  test author and the chosen framework. ``tmt`` wraps around
  frameworks and executes tests of any of them.
* a CI, gating or build system, it runs inside them
* a service, it is a command-line tool and a library
* a provisioning or virtualization tool, it uses libvirt, Podman
  and cloud APIs through plugins
* a configuration-management tool, it uses Ansible and supports
  custom shell scripts for guest preparation
* a test-result management system, but it integrates with several
  of them
* tied to any single programming language, framework, operating
  system, cloud or runtime, and it is not limited to the
  Fedora/RHEL ecosystem
* a monolith, it is a plugin architecture where you use only what
  you need


Guiding Principles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There are two main guiding principles for the decision of whether
a certain functionality belongs to ``tmt`` or not:

Integrate rather than duplicate
    Prefer reusing an existing, mature solution over building the
    same capability again inside ``tmt``.

Plugin over core
    Prefer delivering functionality as a plugin, and extend the
    core only as much as enabling that plugin requires.

The principles above become actionable through a short set of
questions. When a new feature or request is considered, work
through them in order. First decide whether it belongs in ``tmt``
at all:

Is there an existing solution we can integrate or extend instead?
    If a mature tool already does it, prefer integration over
    reimplementation.

Can't we do this outside of tmt?
    If users can already achieve it with existing tools or a thin
    wrapper, it likely does not belong in ``tmt``.

Is it hard to achieve outside of tmt?
    The stronger the case that it is genuinely difficult without the
    orchestration and metadata layer, the stronger the case for
    including it.

Then, if it fits, decide how it should live in ``tmt``:

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


Positioning
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``tmt`` occupies a thin but valuable layer: the metadata and
orchestration layer between test frameworks and CI/CD platforms.
This is the glue that many teams otherwise rebuild ad hoc with
scripts or CI-specific configuration. Where ``tmt`` is
distinctive:

* fmf, hierarchical and inheritable test metadata stored in git
* a generic, provisioner-agnostic hardware requirements language
* one plan running unchanged across container, virtual machine and
  bare metal
* remote test-repository references enabling cross-project sharing
* story-driven coverage, linking features to code, tests and docs
* unified upstream and downstream testing, test once and gate
  everywhere
* ``tmt try``, an interactive mode which provisions an environment
  and lets you experiment, develop and debug tests right there

``tmt`` is the right choice when you test across multiple CI
platforms or environments, need hardware-requirement
specifications, want test definitions versioned next to the code,
or need unified upstream and downstream testing.


Test Framework
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Because ``tmt`` is sometimes mistaken for a test framework, it is
worth clarifying the difference. The key is the scope, or altitude,
at which each of them operates.

``tmt`` works at the operating system level. It provisions a guest,
be it a virtual machine, a container or a bare-metal system,
discovers which tests should run, prepares the whole environment,
for example by installing packages with the system package manager,
applying Ansible playbooks or even rebooting the machine, then
executes the tests and interprets and aggregates their results.

A test framework works inside a single process on that prepared
system, at the level of an individual test case. It provides the
primitives for writing the test logic itself, such as assertions,
expectations and in-process fixtures, deciding what to check and
how. ``pytest`` is a typical example: you write test functions,
express checks with ``assert`` and share setup through fixtures, and
``pytest`` collects and runs them.

For such a case ``tmt`` would provision and prepare the environment,
install ``pytest``, run the suite and report the outcome, while
``pytest`` itself decides what each individual test verifies. Think
of it as a zoom factor. ``tmt`` keeps the wide view, setting up the
stage and orchestrating the run, while the framework zooms in on
each test case with fine-grained detail. The two meet at the
``framework`` key, which tells ``tmt`` only how to interpret a
test's result, currently ``shell`` or ``beakerlib``.


Corner Stones
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These corner stones explain why the tool is shaped the way it is.
They come from the original vision and remain the reference point
for decisions.

Together
--------

Collaboration over silos.

Upstream with downstream
    Wherever possible, use identical or at least similar
    approaches, processes and tools across Fedora, CentOS Stream
    and RHEL. When introducing new concepts and tools, open
    source them as soon as possible. Ideally keep only internal
    configuration downstream, everything else should be consistent
    to minimize maintenance.

Developers with testers
    Tooling should allow, support and encourage developer and
    tester collaboration. All important use cases related to
    developers working together with testers should be prioritized
    and addressed as soon as possible. There should be a simple
    way to run tests locally to easily reproduce issues, develop
    and debug tests.

Metadata with source
    Additional information needed for test execution should be
    stored as close to the test source code as possible. This
    naturally allows efficient maintenance as related data are kept
    at one place, supports version control and developer/tester
    collaboration.

Shared solution
    Instead of duplicating the same or similar tools in individual
    silos, rather work together on a common solution and share the
    benefits.

Well
----

Do it well.

Always-ready tools
    Tools support the Always Ready vision. Continuous integration.
    Release early, release often. Every change tested. No feature
    without a test. Components constantly kept in a good shape,
    integrated and stable thanks to extensive test coverage, ready
    to be released any time. Anything which can be automated is
    automated. Bots are team members.

Quality & review
    Quality is everyone's responsibility and review helps a lot.
    The pull request workflow has proven to provide a very good way
    to do code review and brings additional advantages such as
    automated test results and test coverage reports. Devel and
    tester can collaborate on test coverage including test code
    review. We should strive to introduce the pull request
    workflow wherever it makes sense and emphasize review across
    all our workflows.
