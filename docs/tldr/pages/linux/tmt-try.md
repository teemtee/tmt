# tmt try

> Quickly experiment with tests and environments. See also: `tmt`, `tmt-run`.
> More information: <https://tmt.readthedocs.io/en/stable/stories/cli.html#try>.

- Run a test stored in current working directory:

`cd tests/core/smoke && tmt try`

- Use a specific operating system:

`tmt try fedora-41`

- Try a test in a container:

`tmt try fedora@container`

- Use custom filter to select tests instead of using cwd:

`tmt try --test feature`

- Do nothing, just provision the guest and ask what to do:

`tmt try --ask`

- Explicitly ask for login only if there are tests around:

`tmt try --login`

- List all available options:

`tmt try --help`
