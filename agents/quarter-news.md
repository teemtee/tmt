# Quarter News Generation

Generate a high-level quarterly summary of tmt changes for the `docs/news/` directory.
The audience is tmt users — focus on what matters to someone using the tool, not
developing it.

## Input

The user provides a quarter (e.g. "2026 Q2") and the range of releases it covers
(e.g. "1.71 through 1.75"). If the range is not given, check GitHub releases to
determine which versions fall within the quarter's date range.

## Gathering information

Use two sources and cross-reference them:

1. **Official release notes** at `https://tmt.readthedocs.io/en/stable/releases/index.html`
   — this is the primary source. Fetch it and extract entries for the relevant versions.

2. **GitHub releases** for `teemtee/tmt` — fetch each release by tag (e.g. `1.71.0`).
   These contain the full PR changelog and may mention items not highlighted in the
   official notes.

For items that appear only in the GitHub changelog (not in the official readthedocs
notes), check the actual PR description to understand the change before including it.
Items that are purely internal (CI changes, refactoring without behavioral impact,
test-only changes, dependency updates) should be excluded unless they have a visible
user impact.

## Filtering criteria

Include:

- New features and user-visible enhancements
- Bug fixes that affect user experience (especially those mentioned in the official notes)
- New CLI tools, options, or environment variables
- Specification additions (new keys, new plugins)
- Changes to defaults that users need to be aware of
- Notable improvements to existing plugins

Exclude:

- Internal refactoring without behavioral changes
- CI/CD pipeline changes
- Test-only changes
- Dependency updates (unless they enable new features or noticeably improve performance)
- Internal plumbing (e.g. code extraction into submodules, dataclass conversions)

When in doubt about whether an item is user-relevant, check whether the official
readthedocs release notes mention it. If they do, include it. If they don't and the
PR description describes an internal change, skip it.

## Deduplication with previous quarters

Before finalizing, read the previous quarter's news file (e.g. `docs/news/2026-q1.md`)
and check for overlapping items. Features introduced in a previous quarter should not
be re-announced. If the current quarter extends a previously introduced feature,
frame the entry as a progression ("extended to all phases") rather than presenting
it as new.

## Output format

Save the file as `docs/news/{year}-q{N}.md`. Follow the format of existing files in
`docs/news/` exactly:

- Title: `# tmt news {year} Q{N}`
- Subtitle: `What's new in tmt {first_version}–{last_version}` (use en-dash)
- Sections with `##` headings, grouped by feature area
- Bullet points with `*` (not `-`)
- One blank line between each bullet point
- Include links to the official tmt documentation at `https://tmt.readthedocs.io/en/stable/`
  where relevant. Link to specific plugin pages, specification pages, or guide sections.
  Common link targets:
  - Plugins: `plugins/provision.html#bootc`, `plugins/prepare.html#artifact`
  - Spec: `spec/hardware.html#preset`, `spec/plans.html#/spec/plans/environment`
  - Guide: `guide.html#link-issues`
  - Overview: `overview.html#plugin-variables`
  - Stories: `stories/cli.html#try`, `stories/features.html#/stories/features/reboot`
  - Checks: `plugins/test-checks.html#dmesg`
  - Contribute: `contribute.html#dry-mode`

## Section organization

Group items into sections by feature area. Use short section names. Example sections
(not all are needed every quarter):

- Recipes
- Artifact Verification
- Provisioning & Guests
- Test Execution & Duration
- Test Discovery & Filtering
- Prepare & Artifact Handling
- Integrations & Reporting
- Environment & Hardware
- Framework & Checks
- Beakerlib Libraries
- tmt try
- Other

Put the most important/interesting sections first. Less prominent items (performance
tweaks, minor fixes, packaging changes) go into an "Other" section at the end.

Sections with only one item can be merged into a related section or into "Other".

## Style

- Each bullet starts with a bold-ish lead phrase followed by an em-dash and explanation
- Be concise — one or two sentences per item
- State what changed and why it matters, not how it was implemented
- Use backticks for code, commands, environment variables, file paths, and key names
- Don't use praise, enthusiasm, or exclamation points
