# Performance profiling

Standalone scripts for collecting and summarizing cProfile data for tmt.
Run everything from the repository root.

Shared settings live in `profile_lib.py`

## Common commands

Profile metadata-heavy CLI commands:

```bash
python3 tests/performance/profile_common_commands.py
python3 tests/performance/summarize_profiles.py
```

Edit `COMMANDS` in `profile_common_commands.py` to change what is profiled.
Output goes to `.profile_common_commands/`.

`summarize_profiles.py` ships with a common-commands preset at the top of the
file. With `LABELS = None`, every `.prof` file in the profile directory is
included.

## Synthetic full runs

Build a synthetic fmf tree, profile full plan runs, then summarize:

```bash
python3 tests/performance/create_synthetic_plan.py
python3 tests/performance/profile_synthetic_runs.py
```

Edit the synthetic preset in `summarize_profiles.py` (uncomment the Synthetic full-run preset
block), then run it again.

`profile_synthetic_runs.py` requires the synthetic tree under
`tests/performance/synthetic/`. Edit `PLANS`, `PROVISION_METHODS`, and
`STATE_FORMATS` in that script to change the matrix. The default matrix can
take several hours. Output goes to `.profile_synthetic_runs/`.

## Templates

Jinja sources in `templates/` are rendered by `create_synthetic_plan.py` into
the gitignored `synthetic/` directory.
