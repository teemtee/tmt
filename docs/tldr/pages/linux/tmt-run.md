# tmt run

> Execute tmt test steps. By default, all steps are run.
> See also: `tmt`, `tmt-try`.
> More information: <https://tmt.readthedocs.io/en/stable/overview.html#run>.

- Run all test steps for each plan:

`tmt run`

- Run selected plans and tests:

`tmt run plan -n {{plan name}} test -n {{test name}}`

- Show what tests a specific plan would run:

`tmt run -vv discover plan -n {{plan name}}`

- Show results from the last run in a web browser:

`tmt run -l report --how html --open`

- Add context to a run:

`tmt run --context {{key}}={{value}} -c distro={{fedora}}`

- Select or adjust the provisioning step:

`tmt run -a provision --how=container --image={{fedora:rawhide}}`

- Run test interactively:

`tmt run --all execute --how tmt --interactive`

- Use dry mode to see what actions would happen and use highest verbosity:

`tmt run --dry -vvv`
