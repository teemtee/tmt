# tmt

> Test Management Tool for creating, running and debugging tests. See also: `tmt-run`, `tmt-try`.
> More information: <https://tmt.readthedocs.io>.

- View documentation for `tmt run`:

`tldr tmt-run`

- View documentation for `tmt try`:

`tldr tmt-try`

- Make project tests manageable by `tmt`:

`tmt init`

- Create a new test with optional arguments like template and link:

`tmt create --template beakerlib --link verifies:issue#1234`

- List available tests, plans, or stories:

`tmt <test|plan|story> ls [<pattern>]`

- Validate metadata:

`tmt lint`

- Docs, test & implementation coverage for selected stories:

`tmt story coverage [<pattern>]`

- Use filter:

`tmt tests ls --filter tag:foo --filter tier:0`
