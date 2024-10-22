# tmt run

> `run` command is used to execute test steps. By default all test steps are run. See also: `tmt`, `tmt-try`.
> More information: <https://tmt.readthedocs.io/en/stable/overview.html#run>.

- Run all test steps for each plan:

`tmt run`

- Run selected plans and tests:

`tmt run plan -n <plan_name> test -n <test_name>`

- Show what tests a specific plan would run:

`tmt run -vv discover plan -n <plan_name>`

- Show test results from the last run in a web browser:

`tmt run -l report --how html --open`

- Add context to a test run:

`tmt --context foo=bar --context baz=qux,quux run ...`

- Allow only specific provision plugins:

`tmt run -a provision --allowed-how 'container|local|virtual'`

- Disable output capturing and interact directly with the test from the terminal:

`tmt run --all execute --how tmt --interactive`

- Use dry mode to see what actions would happen and use highest verbosity:

`tmt run --dry -vvv`
