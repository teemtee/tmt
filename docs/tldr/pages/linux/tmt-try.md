# tmt try

> Quickly experiment with tests and environments.
> See also: `tmt`, `tmt-run`.
> More information: <https://tmt.readthedocs.io/en/stable/stories/cli.html#try>.

- Run a test in current directory:

`{{cd path/to/test &&}} tmt try`

- Use a specific operating system:

`tmt try {{fedora-41}}`

- Start an interactive session:

`tmt try fedora@container`

- Select tests with custom filter:

`tmt try --test {{feature}}`

- Provision guest and wait for instructions:

`tmt try --ask`

- Request login if tests are present:

`tmt try --login`

- Display help:

`tmt try --help`
