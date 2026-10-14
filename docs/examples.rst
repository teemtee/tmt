.. _examples:

======================
    Examples
======================

Let's have a look at a couple of real-life examples!

You can obtain detailed list of available options for each command
by invoking it with ``--help``. In order to control the verbosity
of the output use ``--verbose`` and ``--quiet``. To display
implementation details for debugging use the ``--debug`` option.
See :tmt:story:`/stories/cli/common` options for details.

Simply run ``tmt`` to get started with exploring your working
directory:

.. code-block:: shell

    $ tmt
    Found 2 tests: /tests/docs and /tests/ls.
    Found 3 plans: /plans/basic, /plans/helps and /plans/smoke.
    Found 109 stories: /spec/core/description, /spec/core/order,
    /spec/core/summary, /spec/plans/artifact, /spec/plans/gate,
    /spec/plans/summary, /spec/plans/discover and 103 more.



Init
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before starting a new project initialize the metadata tree root:

.. code-block:: shell

    $ tmt init
    Tree '/tmp/try' initialized.
    To populate it with example content, use --template with mini, base or full.

You can also populate it with a minimal plan example:

.. code-block:: shell

    $ tmt init --template mini
    Tree '/tmp/try' initialized.
    Applying template 'mini'.
    Directory '/tmp/try/plans' created.
    Plan '/tmp/try/plans/example.fmf' created.

Create a plan and a test:

.. code-block:: shell

    $ tmt init --template base
    Tree '/tmp/try' initialized.
    Applying template 'base'.
    Directory '/tmp/try/tests/example' created.
    Test metadata '/tmp/try/tests/example/main.fmf' created.
    Test script '/tmp/try/tests/example/test.sh' created.
    Directory '/tmp/try/plans' created.
    Plan '/tmp/try/plans/example.fmf' created.

Initialize with a richer example that also includes the story
(overwriting existing files):

.. code-block:: shell

    $ tmt init --template full --force
    Tree '/tmp/try' already exists.
    Applying template 'full'.
    Directory '/tmp/try/tests/example' already exists.
    Test metadata '/tmp/try/tests/example/main.fmf' overwritten.
    Test script '/tmp/try/tests/example/test.sh' overwritten.
    Directory '/tmp/try/plans' already exists.
    Plan '/tmp/try/plans/example.fmf' overwritten.
    Directory '/tmp/try/stories' created.
    Story '/tmp/try/stories/example.fmf' created.



Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``tests`` command is used to investigate and handle tests.
See the :ref:`specification` for details about the L1 Metadata.


Explore Tests
------------------------------------------------------------------

Use ``tmt tests`` to briefly list discovered tests:

.. code-block:: shell

    $ tmt tests
    Found 2 tests: /tests/docs and /tests/ls.

Use ``tmt tests ls`` to list available tests, one per line:

.. code-block:: shell

    $ tmt tests ls
    /tests/docs
    /tests/ls

Use ``tmt tests show`` to see detailed test metadata:

.. code-block:: shell

    $ tmt tests show
    /tests/docs
         summary Check that essential documentation is working
         contact Petr Šplíchal <psplicha@redhat.com>
            test ./test.sh
            path /tests/docs
        duration 5m
            tier 0
          result respect
         enabled yes

    /tests/ls
         summary List available tests and plans
     description Make sure that 'tmt test ls' and 'tmt plan ls' work.
         contact Petr Šplíchal <psplicha@redhat.com>
            test ./test.sh
            path /tests/ls
        duration 5m
            tier 1
          result respect
         enabled yes

Append ``--verbose`` to get additional information about test as
the list of source files where metadata are defined and its full id:

.. code-block:: shell

    $ tmt tests show /tests/docs --verbose
    /tests/docs
         summary Check that essential documentation is working
         contact Petr Šplíchal <psplicha@redhat.com>
            test ./test.sh
            path /tests/docs
        duration 5m
            tier 0
          result respect
         enabled yes
         sources /home/psss/git/tmt/tests/main.fmf
                 /home/psss/git/tmt/tests/docs/main.fmf
          fmf-id name: /tests/docs
                 url: https://github.com/teemtee/tmt.git


Filter Tests
------------------------------------------------------------------

Both ``tmt tests ls`` and ``tmt tests show`` can optionally filter
tests with a regular expression, filter expression, a Python
condition or link expression:

.. code-block:: shell

    $ tmt tests show docs
    /tests/docs
         summary Check that essential documentation is working
         contact Petr Šplíchal <psplicha@redhat.com>
            test ./test.sh
            path /tests/docs
        duration 5m
            tier 0
          result respect
         enabled yes

    $ tmt tests ls --filter 'tier: 0'
    /tests/docs

    $ tmt tests ls --condition 'tier and int(tier) > 0'
    /tests/ls

    $ tmt tests ls --link verifies:issues/423$
    /tests/prepare/shell

    $ tmt tests ls unit
    /tests/report/junit
    /tests/unit

    $ tmt tests ls unit --exclude junit
    /tests/unit

In order to select tests under the current working directory use
the single dot notation:

.. code-block:: shell

    $ tmt test show .
    $ tmt run test --name .


Import Tests
------------------------------------------------------------------

Use ``tmt tests import`` to gather old metadata stored in
different sources and convert them into the new ``fmf`` format.
By default ``Makefile`` and ``PURPOSE`` files in the current
directory are inspected plus the ``Nitrate`` and ``Polarion`` test
case management systems are contacted to gather all related
metadata.

In order to fetch data from Nitrate you need to have ``nitrate``
module installed. For each test case found in Nitrate separate fmf
file is created with metadata unique to that case. Common metadata
found in all test cases are stored in ``main.fmf``. You can use
``--no-nitrate`` to disable Nitrate integration, ``--no-makefile``
and ``--no-purpose`` switches to disable the other two metadata
sources.

To read data from Polarion you need to install and setup
``pylero`` library (described in `Export tests`_) and enable it
with the ``--polarion`` flag. You can specify ``--polarion-case-id``
instead of searching by values pulled from other sources and you can specify
``--no-link-polarion`` to not save Polarion links. It reads
summary, description, enabled status, assignee, id, component,
tags and links. If ``id`` is not found in Polarion it's generated
and exported.

Argument ``--polarion-case-id`` can be provided multiple times to import
multiple test cases and it supports setting of test names (separated by ``:``),
if test name is not provided ``Polarion WorkItem ID`` is used
and lastly when ``--no-link-polarion`` is used ``summary`` is taken as test name.
Examples how to use the import with multiple cases and test names:

.. code-block:: shell

    $ tmt test import --polarion --polarion-case-id TMT-123:smoke_test .
    ...
    Metadata successfully stored into '/path/to/test/smoke_test.fmf'.

    $ tmt test import --polarion --polarion-case-id TMT-123:smoke_test --polarion-case-id TMT-124:base_test .
    ...
    Metadata successfully stored into '/path/to/test/main.fmf'.
    Metadata successfully stored into '/path/to/test/smoke_test.fmf'.
    Metadata successfully stored into '/path/to/test/base_test.fmf'.

    $ tmt test import --polarion --polarion-case-id TMT-123 --polarion-case-id TMT-124 .
    ...
    Metadata successfully stored into '/path/to/test/main.fmf'.
    Metadata successfully stored into '/path/to/test/TMT-123.fmf'.
    Metadata successfully stored into '/path/to/test/TMT-124.fmf'.

Manual test cases can be imported from Nitrate using the
``--manual`` option. Provide either ``--case ID`` or ``--plan ID``
with the Nitrate test case/plan identifier to select which test
case should be imported or which test plan should be checked for
manual test cases. Directory ``Manual`` will be created in the fmf
root directory and manual test cases will be imported there.

Example output of metadata conversion:

.. code-block:: shell

    $ tmt test import
    Checking the '/home/psss/git/tmt/examples/convert' directory.
    Makefile found in '/home/psss/git/tmt/examples/convert/Makefile'.
    task: /tmt/smoke
    summary: Simple smoke test
    test: ./runtest.sh
    contact: Petr Splichal <psplicha@redhat.com>
    component: tmt
    duration: 5m
    require: fmf
    recommend: tmt
    Purpose found in '/home/psss/git/tmt/examples/convert/PURPOSE'.
    description:
    Just run 'tmt --help' to make sure the binary is sane.
    This is really that simple. Nothing more here. Really.
    Nitrate test case found 'TC#0603489'.
    extra-summary: tmt convert test
    contact: Petr Šplíchal <psplicha@redhat.com>
    environment:
    {'TEXT': 'Text with spaces', 'X': '1', 'Y': '2', 'Z': '3'}
    tag: ['NoRHEL4', 'NoRHEL5', 'Tier3']
    tier: 3
    component: tmt
    enabled: True
    adjust:
      - enabled: false
        when: distro ~= rhel-4, rhel-5
        continue: false
      - environment:
            PHASES: novalgrind
        when: arch == s390x
        continue: false
    Metadata successfully stored into '/home/psss/git/tmt/examples/convert/main.fmf'.

And here's the resulting ``main.fmf`` file:

.. code-block:: yaml

    summary: Simple smoke test
    description: |
        Just run 'tmt --help' to make sure the binary is sane.
        This is really that simple. Nothing more here. Really.
    contact: Petr Šplíchal <psplicha@redhat.com>
    component:
    - tmt
    test: ./runtest.sh
    require:
    - fmf
    recommend:
    - tmt
    environment:
        TEXT: Text with spaces
        X: '1'
        Y: '2'
        Z: '3'
    duration: 5m
    enabled: true
    tag:
    - NoRHEL4
    - NoRHEL5
    - Tier3
    tier: '3'
    adjust:
      - enabled: false
        when: distro ~= rhel-4, rhel-5
        continue: false
      - environment:
            PHASES: novalgrind
        when: arch == s390x
        continue: false
    extra-summary: tmt convert test
    extra-task: /tmt/smoke
    extra-nitrate: TC#0603489


Export Tests
------------------------------------------------------------------

Use ``tmt tests export`` command to export test metadata into
different formats and tools. By default all available tests are
exported, specify regular expression matching test name to export
only selected tests or use ``.`` to export tests under the current
directory:

.. code-block:: shell

    $ tmt tests export --how nitrate .
    Test case 'TC#0603489' found.
    summary: tmt convert test
    script: /tmt/smoke
    components: tmt
    tags: NoRHEL4 Tier3 NoRHEL5 fmf-export
    default tester: psplicha@redhat.com
    estimated time: 5m
    status: CONFIRMED
    arguments: TEXT='Text with spaces' X=1 Y=2 Z=3
    Structured Field:
    distro = rhel-6: False
    description: Simple smoke test
    purpose-file: Just run 'tmt --help' to make sure the binary is sane.
    This is really that simple. Nothing more here. Really.
    fmf id:
    name: /
    path: /examples/convert
    url: https://github.com/teemtee/tmt.git
    Test case 'TC#0603489' successfully exported to nitrate.

    $ tmt test export --how polarion --project-id TMT --create .
    Test case 'TMT-42' created.
    title: This is case what already exists inside polarion
    description: tmt /existing_testcase - This is case what already exists inside polarion
    script: https://github.com/teemtee/tmt.git
    components: tmt
    tags: integration fmf-export
    enabled: True
    Append the Polarion test case link.
    implements: https://polarion.example/polarion/#/project/TMT/workitem?id=TMT-42
    Test case 'This is case what already exists inside polarion' successfully exported to Polarion.

    $ tmt test export --how jira --create \
        --jira-url https://example.atlassian.net \
        --jira-user me@example.com --jira-token TOKEN \
        --project-id TESTS --jira-uuid-field 'tmt UUID' .
    Test case 'TESTS-100' created.
    summary: /tests/core/smoke
    uuid: 785d9b62-1111-2222-3333-444455556666
    components: tmt

Before export to ``--how nitrate`` tmt checks that used test
metadata are committed to git and present on ``origin`` remote.
On own risk the failure can be ignored with ``--ignore-git-validation``.

Nitrate test case can be created from test metadata with ``--create``.
By default existing cases are detected each time, if you need to
create additional nitrate test case use ``--duplicate``.
Export will append ``extra-nitrate`` to the test metadata.
Those changes have to be committed and pushed manually.

To include nitrate test case in general plans use ``--general``.
Set of general plans to which the test case will be linked is
detected from the :tmt:story:`/spec/tests/component`. Any additional
general plan will be removed.

For newly created nitrate test case it can be useful to add it
to all open nitrate test runs under its general plans. This can be
done using the ``--link-runs`` option.

Use the ``--bugzilla`` option together with ``--how nitrate``,
``--how polarion`` to link bugs marked as ``verifies``
in the :tmt:story:`/spec/core/link` attribute with the corresponding
Nitrate/Polarion test case. Jira uses configured relation mappings.

Almost all important attributes should be pulled from fmf metadata
both for Nitrate and Polarion including: Title, Description,
Author, Assignee, Automation, Automation script, Level, Component,
Test type, Tags, Importance, Status, Linked BZs and possibly more
in the future.

Also a unique id generated by tmt (automatically during export) is
added into Notes (Nitrate), tmt ID (Polarion) or a configured Jira field for
matching cases across all test case management systems.

Configuration and guide for setting up nitrate can be found
at https://github.com/psss/python-nitrate

Configuration and guide for setting up pylero can be found
at https://github.com/RedHatQE/pylero

.. _jira-project-configuration:

Jira Project Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

The Jira exporter supports **Jira Cloud**, using REST v3, ADF descriptions
and HTTP Basic Auth with an email address and API token. Install the
``tmt[link-jira]`` extra (or ``tmt+link-jira`` system package). Existing
``tmt link`` consumers retain the SDK's Server/Data Center behavior;
Server/Data Center export is not supported by this plugin.
Cloud UUID lookup uses the supported ``search/jql`` endpoint through the SDK's
authenticated transport, including Jira SDK 3.5 on Python 3.9. It follows token
pagination to detect ambiguous UUID matches even across response pages.

Choose a project and a searchable custom text field for the tmt UUID.
The UUID field must support equality searches with ``cf[NUMBER]`` in JQL.
Configure these with ``--project-id`` and ``--jira-uuid-field`` or in the
``/export/jira`` node of the existing tmt configuration tree. For example,
create ``export/jira.fmf`` under ``~/.config/tmt`` (or ``TMT_CONFIG_DIR``),
with the directory initialized as an fmf tree:

.. code-block:: yaml

    project: TESTS
    issue-type: Task
    uuid-field: tmt UUID
    automation-url: remote-link
    title: '{summary}'
    # Optional target status; enabled/disabled metadata does not select status.
    status: null
    managed-fields: [summary, description, components, labels, assignee]
    fields: {}
    links: {}

Credentials are supplied through ``--jira-url``, ``--jira-user`` and
``--jira-token`` or ``TMT_JIRA_URL``, ``TMT_JIRA_USER`` and ``TMT_JIRA_TOKEN``.
Explicit credential options override environment variables. Missing connection
values can also come from a matching Jira issue tracker in the user's existing
``/link`` settings. With multiple configured connections, select a URL explicitly.
Tokens and connection credentials are not accepted in shareable schema profiles.

Use repeatable ``--jira-profile PATH`` options to distribute YAML mappings
without replacing ``TMT_CONFIG_DIR``. Precedence, from lowest to highest, is:
user ``/export/jira`` defaults, profile files in command-line order, explicit
schema options. Nested mappings merge; lists and scalars replace earlier values.
An explicitly empty mapping (for example ``links: {}``) clears inherited entries.
A team profile and a small repository override can therefore be applied with:

.. code-block:: shell

    tmt tests export --how jira --create \
        --jira-profile /opt/team/rheltest.yaml --jira-profile ./jira.yaml

A repository override can contain just ``title: '{name}'`` and
``managed-fields: [summary, description, components]`` to preserve
Jira-maintained labels and assignees. Explicit CLI schema options override
the layered configuration:

.. list-table:: Jira schema options
   :header-rows: 1

   * - Option
     - Configuration key and behavior
   * - ``--project-id``
     - ``project``: project key, required
   * - ``--jira-issue-type``
     - ``issue-type``: ID or name available in the project; default ``Task``
   * - ``--jira-uuid-field``
     - ``uuid-field``: custom field ID or unique name, required
   * - ``--jira-automation-url``
     - ``automation-url``: field ID/name, ``remote-link`` (default), or ``none``
   * - ``--jira-title``
     - ``title``: format supporting ``{name}`` and ``{summary}``; default ``{summary}``
   * - ``--jira-status``
     - ``status``: optional target status; ``none`` disables a configured transition

Field names must be unique across the visible Jira schema. An ambiguous
name fails with the candidate IDs; configure the exact ``customfield_N``
instead. The exporter does not guess which field applies to a project.
Issue types resolve within the chosen project. Preparation checks payload fields
against create or edit metadata, required values, and exposed select options.
Configured relationship type names and same-instance targets are checked too.
Exposed choices can be scalars or objects with ``id``, ``value`` or ``name``.
Payload choices use the same normalization; option IDs remain distinct from
display values, and combined ID/value selections must describe one option.
Unsupported choice shapes fail with an ``ExportError`` during preparation.
An existing issue's transition fails if none or multiple transitions lead to
the configured status. For a new issue, preparation validates that the status
belongs to its project/type workflow; the transition ID can only be resolved
after creation. Conditional workflow rules can still reject that transition.

UUID lookup is scoped to project and issue type and never includes
components. Multiple UUID matches fail explicitly. Jira ``implements``
backlinks are also checked for project, type and conflicting UUIDs; multiple
candidate issues fail. Collection uniqueness is checked after all identities
have been resolved: two tests cannot share a restored/generated UUID or target
one issue even when their local UUIDs differ. Existing local UUIDs are preserved. If metadata
has no UUID, a linked issue's UUID is restored, otherwise one is generated
and persisted. ``--duplicate`` is rejected because Jira identity must be
unique. ``--create`` permits new issues; otherwise a missing issue fails.

The whole selected collection is checked for committed, published metadata
before UUID generation or optional backlink writes. Preparation then resolves
all identities in memory, builds enriched payloads, and validates fields,
relationships and transitions for the entire collection. Application starts
only after preparation succeeds. Invalid titles or late mapping errors therefore
leave metadata and Jira untouched. Virtual tests can share source files
without failing on the exporter's own writes. Validation
covers the initial collection; it is not a lock against concurrent edits.
``--ignore-git-validation`` permits unpublished metadata and still constructs
an automation URL when possible. ``--link-jira`` adds an ``implements`` link
to local metadata; it is disabled by default. Commit and publish generated
UUIDs or requested backlinks before the next validated export.

``managed-fields`` selects ordinary Jira fields owned by tmt. The default is
``[summary, description, components, labels, assignee]``; omitted fields are
preserved, and ``[]`` preserves all ordinary fields on updates. Jira still
requires a title on creation, even when ``summary`` is not managed thereafter.
UUID identity is always managed, and configured automation/additional fields
remain managed independently of this list. Owned fields use replacement
semantics, including clearing removed components rather than accumulating them:

.. list-table:: Field ownership
   :header-rows: 1

   * - Destination
     - Source and empty-value behavior
   * - Summary
     - Resolved fmf ``summary`` by default, falling back to the resolved fmf name;
       configurable with ``title`` independently of Description
   * - Description
     - Resolved fmf description; empty clears the field
   * - UUID custom field
     - Existing, restored or generated UUID; never cleared
   * - Components / labels
     - Resolved ``component`` / ``tag`` lists; empty lists clear previous values
   * - Assignee
     - First contact, resolved by full display name or email; empty clears it.
       An unresolved or ambiguous nonempty contact warns and preserves assignment.
       Exact email matches take precedence over display names/usernames; all
       account decisions are cached for one client, including misses and ambiguity
   * - Automation URL field
     - ``Test.web_link()``; unavailable URL clears a configured field
   * - Automation remote link
     - Updated by stable ``globalId=tmt:uuid:UUID``; unavailable URL removes this
       managed link and preserves unrelated remote links
   * - Additional configured fields
     - Resolved scalar source; absent or empty metadata clears the field

Project and issue type are set on creation only. Unconfigured fields and
disabled automation destinations are left untouched. Changing a profile's
field destinations does not remove values from previously managed fields.
Configured relationship links are additive and deduplicated: the exporter
preserves historical links when the source relation disappears. Same-instance
issue links are deduplicated by type, direction and target; remote links by
URL. An extension can implement a different relationship cleanup policy.

Additional field mappings support scalar sources ``tier``, ``summary``,
``description`` and ``name``, with ``text`` and ``single-select`` encodings.
A select value becomes ``{"value": "SOURCE"}`` and must already be an option
in Jira. Optional ``values`` translates explicit source strings to destination
strings; if supplied, an unmapped nonempty source fails. No tier labels or
site-specific field IDs are generated automatically.

For example, an **internal RHELTEST consumer profile** can use the fmf
summary as the title, preserve the description, and map tier to a
single-select field while keeping the components already present in metadata:

.. code-block:: yaml

    project: RHELTEST
    issue-type: Test Case
    uuid-field: ID
    automation-url: URL
    title: '{summary}'
    status: Active
    fields:
      Tier:
        source: tier
        type: single-select
        # If Jira option names differ from fmf tier strings, configure values.
        # values: {'1': 'First', '2': 'Second'}
    links:
      verifies:
        issue-type: Tests
        direction: outward
        remote: true

This is a consumer example, not an upstream default. Use exact field IDs
where names are ambiguous and adapt option values to the instance. Leave
``--link-jira`` disabled to keep metadata backlinks disabled. No ``tmt link``
step is needed.

Relation mapping ``direction: outward`` means the exported case is the
source of the configured Jira relationship (for example, case tests
requirement). ``inward`` reverses the relationship. ``remote: true`` also
exports local HTTP/HTTPS targets as web links, including existing Bugzilla
or Polarion URLs. Structured fmf identifiers are skipped. There are no live
Polarion lookups or special Bugzilla/Red Hat migration rules in this exporter.

An external extension can subclass ``JiraExporter`` and register another
export format using ``Test.provides_export``. Override either public hook:

* ``enrich_payload(test, context, fields)`` mutates the create/update payload
  during preparation and is also called for dry runs. It must preserve
  identity and create routing fields and perform no local or external writes,
  even when preparing a live export.
* ``post_export(test, context)`` runs after CRUD, transitions, relationships
  and optional backlinks. It also runs for dry runs. Extensions must check
  ``context.dry_run`` before performing any local or external writes.

Both receive the resolved ``Test`` and ``JiraExportContext``, containing the
Jira connection, profile, project, issue type ID, resolved field IDs, UUID,
automation URL, dry-run state and issue key. The key is available before
enrichment on updates and after creation for new issues. It is ``None`` for
a dry run of a new issue. ``prepare_test_collection()`` returns typed
``JiraExportPlan`` objects without generic exporter writes; ``to_dict()``
provides their credential-free YAML/JSON representation.
``apply_test_collection()`` applies those prepared operations or displays the
plans in dry mode. Hook exceptions propagate; already completed Jira writes
are not rolled back. Application errors report completed tests and warn of
possible partial writes in the current test. Persisted UUIDs support retries.
Jira export is not transactional across tests or protected from concurrent
Jira/schema changes between preparation and application.

See ``examples/plugins/jira_export.py`` for a small extension that adds a
label and handles a post-export action without replacing discovery, UUID
lookup or Jira CRUD. Load it with ``TMT_PLUGINS=examples/plugins`` and use
``--how jira-example`` with the same Jira options/profile. Cross-system
migration logic belongs in such an external extension. ``--dry`` allows
schema and identity reads, prepares the same fields and operations and invokes
both hooks, but makes no Jira or metadata writes in the generic exporter.
Normal dry-run output shows YAML containing resolved destinations, create/update
decisions, field replacements and clears, automation URL, relationships,
transition status/ID, and planned UUID/backlink metadata writes.

This plugin exports test metadata; it does not report execution results.
Future report plugins can reuse the public, read-only
``JiraInstance.find_issue_by_uuid(uuid, project_id=..., issue_type=..., uuid_field=...)``
lookup with IDs or configured names. Backlinks remain an exporter concern.
Result issue types, grouping and outcome workflows belong in a separate report
step, rather than metadata enrichment or post-export hooks.


BeakerLib Libraries
------------------------------------------------------------------

In order to prevent unnecessary test code duplication it makes
sense to use a test library which implements frequently repeated
actions. Currently beakerlib libraries are supported. They can be
defined in the :tmt:story:`/spec/tests/require` attribute and are
fetched during the :tmt:story:`/spec/plans/discover` step.

Use the short backward-compatible syntax to fetch libraries from
the `default repository`__:

.. code-block:: yaml

    require: library(openssl/certgen)

__ https://github.com/beakerlib/

The full fmf identifier allows to fetch libraries from arbitrary
location:

.. code-block:: yaml

    require:
      - type: library
        url: https://github.com/beakerlib/openssl
        name: /certgen

See the :tmt:story:`/spec/tests/require` attribute specification for
detailed description of the syntax and available keys.



Plans
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``plans`` command is used to investigate and handle plans.
See the :ref:`specification` for details about the L2 Metadata.


Explore Plans
------------------------------------------------------------------

Exploring ``plans`` is similar to using ``tests``:

.. code-block:: shell

    $ tmt plans
    Found 3 plans: /plans/basic, /plans/helps and /plans/smoke.

Use ``tmt plans ls`` and ``tmt plans show`` to output plan names
and detailed plan information, respectively:

.. code-block:: shell

    $ tmt plans ls
    /plans/basic
    /plans/helps
    /plans/smoke

    $ tmt plans show
    /plans/basic
         summary Essential command line features
        discover
             how fmf
      repository https://github.com/teemtee/tmt
        revision devel
          filter tier: 0,1
         prepare
             how ansible
        playbook ansible/packages.yml

    /plans/helps
         summary Check help messages
        discover
             how shell

    /plans/smoke
         summary Just a basic smoke test
         execute
             how shell
          script tmt --help

Verbose output and filtering are similar as for exploring tests.
See `Explore Tests`_ and `Filter Tests`_ for more examples.


.. _multiple-configs:

Multiple Configs
------------------------------------------------------------------

Step can contain multiple configurations. In this case provide
each config with a unique name. Applying ansible playbook and
executing custom script in a single :tmt:story:`/spec/plans/prepare`
step could look like this:

.. code-block:: yaml

    prepare:
      - name: packages
        how: ansible
        playbook: ansible/packages.yml
      - name: services
        how: shell
        script: systemctl start service

Another common use case which can be easily covered by multiple
configs can be fetching tests from multiple repositories during
the :tmt:story:`/spec/plans/discover` step:

.. code-block:: yaml

    discover:
      - name: upstream
        how: fmf
        url: https://github.com/teemtee/tmt
      - name: fedora
        how: fmf
        url: https://src.fedoraproject.org/rpms/tmt/


Extend Steps
------------------------------------------------------------------

When defining multiple configurations for a step it is also
possible to make use of fmf inheritance. For example the common
preparation config can be defined up in the hierarchy:

.. code-block:: yaml

    prepare:
      - name: tmt
        how: install
        package: tmt

Extending the prepare config in a child plan to install additional
package then could be done in the following way:

.. code-block:: yaml

    prepare+:
      - name: pytest
        how: install
        package: python3-pytest

Eventually, use :tmt:story:`/spec/core/adjust` to extend the step
conditionally:

.. code-block:: yaml

    adjust:
      - when: distro == fedora
        prepare+:
          - name: pytest
            how: install
            package: python3-pytest


.. _parametrize-plans:

Parametrize Plans
------------------------------------------------------------------

It is possible to parametrize plans using environment variables and
context. This may be useful to reduce duplication, for example in
CI systems.

For :tmt:story:`/spec/plans/environment` variables the syntax is
standard, both ``$var`` and ``${var}`` may be used. The values of
variables are taken from the ``--environment`` command line option
and the ``environment`` plan attribute. If a variable is defined
using both the attribute and the option, the value from the
``--environment`` option has a priority:

.. code-block:: yaml

    discover:
        how: fmf
        url: https://github.com/teemtee/${REPO}

    $ tmt run -e REPO=tmt

Variables can be also utilized to pick tests from specific discovery phase.
The command line (``tmt run tests --name ...``) applies for the whole discovery
step and would select more tests than required in the case the test names are not unique:

.. code-block:: yaml

    discover:
      - how: fmf
        url: https://github.com/teemtee/tmt.git
        test: ${PICK_TMT}
      - how: fmf
        url: https://github.com/teemtee/fmf.git
        test: ${PICK_FMF}

    $ tmt run -e PICK_TMT='^/tests/core/ls$' -e PICK_FMF='^/tests/(unit|basic/ls)$'

For :tmt:story:`context</spec/context>` parametrization the syntax is
``$@dimension`` or ``$@{dimension}``. The values are set according
to the defined context specified using ``--context`` command line
option and the ``context`` plan attribute:

.. code-block:: yaml

    context:
        branch: main
    discover:
        how: fmf
        url: https://github.com/teemtee/tmt
        ref: $@{branch}

    $ tmt -c branch=tmt run


.. _dynamic-ref:

Dynamic ``ref`` Evaluation
------------------------------------------------------------------

When using test branching for test maintenance it becomes handy to
be able to set :ref:`ref</plugins/discover/fmf>` dynamically
depending on the provided :tmt:story:`/spec/context`. This is possible
using a special file in tmt format stored in a default branch of a
tests repository. That special file should contain rules assigning
attribute ``ref`` in an ``adjust`` block depending on the context.

Dynamic ``ref`` assignment is enabled whenever a test plan reference
has the format ``ref: @FILEPATH``.

Example of a test plan:

.. code-block:: yaml

    discover:
        how: fmf
        url: https://github.com/teemtee/repo
        ref: "@.tmtref"

Example of a dynamic ``ref`` definition file in ``repo/.tmtref``:

.. code-block:: yaml

    ref: main
    adjust:
      - when: distro == centos-stream-9
        ref: rhel-9
      - when: distro == fedora
        ref: fedora
      - when: distro == rhel-9
        ref: rhel-9

The definition file can also be parametrized using environment
variables or context dimensions:

.. code-block:: yaml

    ref: main
    adjust:
      - when: distro == fedora or distro == rhel
        ref: $@distro


Stories
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``stories`` command is used to investigate and handle stories.
See the :ref:`specification` for details about the L3 Metadata.


Explore Stories
------------------------------------------------------------------

Exploring ``stories`` is quite similar to using ``tests`` or
``plans``:

.. code-block:: shell

    $ tmt stories
    Found 109 stories: /spec/core/description, /spec/core/order,
    /spec/core/summary, /spec/plans/artifact, /spec/plans/gate,
    /spec/plans/summary, /spec/plans/discover and 102 more.

The ``tmt stories ls`` and ``tmt stories show`` commands output
the names and the detailed information, respectively:

.. code-block:: shell

    $ tmt stories ls
    /spec/core/description
    /spec/core/order
    /spec/core/summary
    ...

    $ tmt stories show
    /spec/core/description
         summary Detailed description of the object
           story I want to have common core attributes used consistently
                 across all metadata levels.
     description Multiline ``string`` describing all important aspects of
                 the object. Usually spans across several paragraphs. For
                 detailed examples using a dedicated attributes 'examples'
                 should be considered.
     ...

Verbose output and filtering are similar as for exploring tests.
See `Explore Tests`_ and `Filter Tests`_ for more examples.


Filter Stories
------------------------------------------------------------------

Additionally, and specifically to stories, special flags are
available for binary status filtering:

.. code-block:: shell

    $ tmt stories show --help | grep only
      -i, --implemented    Implemented stories only.
      -I, --unimplemented  Unimplemented stories only.
      -t, --verified       Stories verified by tests.
      -T, --unverified     Stories not verified by tests.
      -d, --documented     Documented stories only.
      -D, --undocumented   Undocumented stories only.
      -c, --covered        Covered stories only.
      -C, --uncovered      Uncovered stories only.

    $ tmt stories ls --implemented
    /spec/core/summary
    /stories/api/plan/attributes/artifact
    /stories/api/plan/attributes/gate
    ...

    $ tmt stories show --documented
    /stories/cli/common/debug
         summary Print out everything tmt is doing
           story I want to have common command line options consistently used
                 across all supported commands and subcommands.
         example tmt run -d
                 tmt run --debug
     implemented /tmt/cli
      documented /tmt/cli
    ...

In order to select stories under the current working directory use
the single dot notation:

.. code-block:: shell

    $ tmt story show .


Story Coverage
------------------------------------------------------------------

Current status of the code, test and documentation coverage can be
checked using the ``tmt story coverage`` command:

.. code-block:: shell

    $ tmt story coverage
    code test docs story
    todo todo todo /spec/core/description
    todo todo todo /spec/core/order
    done todo todo /spec/core/summary
    ...
    done todo todo /stories/cli/usability/completion
     39%   9%   9% from 109 stories



Status
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``status`` command is used to inspect the progress of runs,
plans and steps that have previously been started:

.. code-block:: shell

    $ tmt status
    status     id
    prepare    /var/tmp/tmt/run-002
    done       /var/tmp/tmt/run-001


Verbosity Levels
------------------------------------------------------------------

With no verbosity (the default), the status of whole runs is
displayed as shown above. The last done step is shown as the run
status (or 'done' if all enabled steps are completed). With more
verbosity (-v), the status of plans in runs is shown:

.. code-block:: shell

    $ tmt status -v
    status     id
    prepare    /var/tmp/tmt/run-002  /base
    done       /var/tmp/tmt/run-001  /advanced
    done       /var/tmp/tmt/run-001  /base

With the highest verbosity (-vv), the status of individual steps
for each plan is displayed:

.. code-block:: shell

    $ tmt status -vv
    disc prov prep exec repo fini  id
    done done done todo todo todo  /var/tmp/tmt/run-002  /base
    done done done done todo done  /var/tmp/tmt/run-001  /advanced
    done done done done todo done  /var/tmp/tmt/run-001  /base


Status Filtering
------------------------------------------------------------------

The runs shown in the status are by default taken from
``/var/tmp/tmt``. The directory containing runs can be specified
using an argument to ``tmt status``:

.. code-block:: shell

    $ tmt status /tmp/run
    status     id
    done       /tmp/run/001

Status of one specific run can also be shown using the ``--id``
option:

.. code-block:: shell

    $ tmt status -vv --id run-002
    disc prov prep exec repo fini  id
    done done done todo todo todo  /var/tmp/tmt/run-002  /base

Runs and plans can also be filtered based on their status. Option
``--abandoned`` can be used to list runs/plans which have
provision step completed but finish step not yet done. This is
useful for finding active containers or virtual machines:

.. code-block:: shell

    $ tmt status --abandoned
    status     id
    prepare    /var/tmp/tmt/run-002

To show only completed runs/plans, ``--finished`` can be used:

.. code-block:: shell

    $ tmt status --finished
    status     id
    done       /var/tmp/tmt/run-001

Finally, ``--active`` displays runs/plans in progress (at least
one enabled step has not been finished):

.. code-block:: shell

    $ tmt status --active
    status     id
    prepare    /var/tmp/tmt/run-002



Clean
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When running tests, a lot of metadata can gather over time taking
a lot of space. It may be useful to clean it every now and then
using the ``clean`` command. Its goal is to stop the running
guests, remove working directories or remove images. Without any
subcommand, all of these actions are done:

.. code-block:: shell

    $ tmt clean
    clean
        guests
        runs
        images
            testcloud

It may be useful to see exactly which runs are affected using
the ``--verbose`` option:

.. code-block:: shell

    $ tmt clean -v
    clean
        guests
            Stopping guests in run '/var/tmp/tmt/run-001' plan '/base'.
        runs
            Removing workdir '/var/tmp/tmt/run-003'.
            Removing workdir '/var/tmp/tmt/run-002'.
            Removing workdir '/var/tmp/tmt/run-001'.
        images
            testcloud
                warn: Directory '/var/tmp/tmt/testcloud/images' does not exist.

However, before cleaning up all available metadata, you may want
to see what would actually happen using ``--dry`` mode:

.. code-block:: shell

    $ tmt clean -v --dry
    clean
        guests
            Would stop guests in run '/var/tmp/tmt/run-001' plan '/advanced'.
            Would stop guests in run '/var/tmp/tmt/run-001' plan '/base'.
        runs
            Would remove workdir '/var/tmp/tmt/run-002'.
            Would remove workdir '/var/tmp/tmt/run-001'.
        images
            testcloud
                warn: Directory '/var/tmp/tmt/testcloud/images' does not exist.

You may also want to clean everything in only one run using
the ``--id`` or ``--last`` options.

.. code-block:: shell

    $ tmt clean -v --last
    clean
    guests
        Stopping guests in run '/var/tmp/tmt/run-001' plan '/plans/testcloud'.
            finish

                guest: stopped
                guest: removed
                summary: 0 tasks completed
    runs
        Removing workdir '/var/tmp/tmt/run-001'.
    images
        testcloud
            warn: Directory '/var/tmp/tmt/testcloud/images' does not exist.

You can also skip cleaning selected resources using the ``--skip``
option.

.. code-block:: shell

    $ tmt clean -v --last --skip images
    clean
    guests
        Stopping guests in run '/var/tmp/tmt/run-001' plan '/plans/testcloud'.
            finish

                guest: stopped
                guest: removed
                summary: 0 tasks completed
    runs
        Removing workdir '/var/tmp/tmt/run-001'.

In some cases, you may want to have a bit more control over the
behaviour which can be achieved using subcommands and their
options. All of the options described above can be used with
individual subcommands too.


Clean guests
------------------------------------------------------------------

The subcommand ``clean guests`` aims to stop all running guests.
By default, runs are taken from ``/var/tmp/tmt``, this can be
changed using ``--workdir-root`` option of the subcommand:

.. code-block:: shell

    $ tmt clean guests -v --workdir-root /tmp/run
    clean
        guests
            Stopping guests in run '/tmp/run/002' plan '/advanced'.
            Stopping guests in run '/tmp/run/002' plan '/base'.

You may also want to clean the guests in only one run using
``--id`` or ``--last`` options. This serves as an alternative
to ``tmt run --last finish``:

.. code-block:: shell

    $ tmt clean guests -v --last
    clean
        guests
            Stopping guests in run '/var/tmp/tmt/run-003' plan '/advanced'.
            Stopping guests in run '/var/tmp/tmt/run-003' plan '/base'.

The type of provision to be cleaned can be changed using
``--how`` option:

.. code-block:: shell

    $ tmt run provision -h container
    /var/tmp/tmt/run-001
    ...

    $ tmt run provision -h virtual
    /var/tmp/tmt/run-002
    ...

    $ tmt clean guests --how container
    clean
        guests
            Stopping guests in run '/var/tmp/tmt/run-001' plan '/advanced'.
            Stopping guests in run '/var/tmp/tmt/run-001' plan '/base'.

    $ tmt clean guests --how virtual
    clean
        guests
            Stopping guests in run '/var/tmp/tmt/run-002' plan '/advanced'.
            Stopping guests in run '/var/tmp/tmt/run-002' plan '/base'.


Clean workdirs
------------------------------------------------------------------

The goal of ``clean runs`` is to remove workdirs of past runs.
Similarly to above, ``/var/tmp/tmt`` is used by default as run
location and this can be changed using ``--workdir-root`` option:

.. code-block:: shell

    $ tmt clean runs --workdir-root /tmp/run
    clean
        runs
            Removing workdir '/tmp/run/001'.

Only one specific run can also be removed using ``--id`` or
``--last`` options, similarly to ``clean guests``:

.. code-block:: shell

    $ tmt clean runs -v -i /var/tmp/tmt/run-001
    clean
        runs
            Removing workdir '/var/tmp/tmt/run-001'.

You may also want to remove only old runs. This can be achieved
using ``--keep`` option which allows you to specify the number
of latest runs to keep:

.. code-block:: shell

    $ for i in $(seq 1 10); do tmt run; done
    ...

    $ tmt clean runs --dry -v --keep 5
    clean
        runs
            Would remove workdir '/var/tmp/tmt/run-005'.
            Would remove workdir '/var/tmp/tmt/run-004'.
            Would remove workdir '/var/tmp/tmt/run-003'.
            Would remove workdir '/var/tmp/tmt/run-002'.
            Would remove workdir '/var/tmp/tmt/run-001'.


Clean images
------------------------------------------------------------------

The subcommand ``clean images`` removes images of all provision
methods that support it. Currently, only testcloud provision
supports this option, the images are removed from
``/var/tmp/tmt/testcloud/images``:

.. code-block:: shell

    $ tmt clean images
    clean
        images
            testcloud
                Removing '/var/tmp/tmt/testcloud/images/Fedora-Cloud-Base-34_Beta-1.3.x86_64.qcow2'.


Coding
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to perform more advanced processing of the metadata
which is not supported by the command line use Python. To get
quickly started just import the ``tmt`` module and grow a new
``tmt.Tree`` object:

.. code-block:: python

    import tmt

    tree = tmt.Tree.grow()

    for test in tree.tests():
        print(test.name)

Use the ``tmt.utils.Path`` class when specifying paths:

.. code-block:: python

    from tmt.utils import Path

    tree = tmt.Tree.grow(path=Path("/path/to/the/tree"))

Some functions and methods require a ``logger`` instance. Creating
it and enabling more detailed logging to console is simple:

.. code-block:: python

    import tmt.log
    import tmt.utils

    # Create a new logger with the desired debug/verbosity level
    logger = tmt.log.Logger.create(debug=3, verbose=3)

    # Add a console handler to show debugging output on the terminal
    logger.add_console_handler()

    tmt.utils.git.git_clone(
        url="https://github.com/teemtee/tmt/",
        destination="/tmp/something",
        logger=logger)
