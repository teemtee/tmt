# Release Notes Generation

When creating release notes for tmt, use the milestone name as input (e.g., "1.65") and follow these guidelines:

1. **Find PRs**: Use the [tmt sprint board](https://github.com/orgs/teemtee/projects/1) to find **merged** pull requests for the specified milestone. Only consider PRs from the `teemtee/tmt` repository. Ignore PRs that are not yet merged.

2. **Check existing entries**: Review the fmf files in the `docs/releases/` directory:
   - Release notes are stored as individual fmf files with a `description` key
   - Each version has its own subdirectory (e.g., `docs/releases/1.64.0/`)
   - Pending release notes are in `docs/releases/pending/`
   - Files are named after the issue/PR number (e.g., `4465.fmf`)

3. **Format requirements**:
   - Create new fmf files directly in the release directory (e.g., `docs/releases/1.65.0/`)
   - Create the release directory if it doesn't exist
   - Use the issue/PR number as the filename (e.g., `1234.fmf`)
   - Include a `description` key with the release note text in reStructuredText format
   - Be concise but descriptive
   - Skip PRs that already have release notes added
   - Focus on user-facing changes and improvements

4. **Content guidelines**:
   - Include new features and enhancements
   - Document bug fixes that affect user experience
   - Mention API changes or deprecations
   - Note any breaking changes
   - Include plugin improvements and new capabilities
   - **Skip** the following types of PRs (no release note needed):
     - CI/CD pipeline changes
     - Test-only changes (unless fixing user-reported issues)
     - Internal refactoring without behavioral changes
     - Documentation typo fixes
     - Dependency updates (unless they enable new features)

5. **Structure**: Each fmf file should follow this pattern:
   ```yaml
   description: |
     Brief description of the change in reStructuredText format.
     Use ``code`` for inline code and :ref:`/path/to/doc` for references.
   ```

   **Examples** (from existing release notes):

   *Simple feature addition* (PR #4320):
   ```yaml
   description: |
     The guest data is now saved in the ``results.yaml`` for each phase execution.
   ```

   *Bug fix with context* (PR #4125):
   ```yaml
   description: |
     The :ref:`/plugins/provision/virtual.testcloud` plugin now works
     with the ``debian`` images as well thanks to refreshing package
     metadata before trying to install ``rsync`` on the guest.
   ```

   *New command-line option* (PR #4231):
   ```yaml
   description: |
     Introduced option ``--import-before-name-filter`` and equivalent
     environment variable ``TMT_IMPORT_BEFORE_NAME_FILTER`` which imports
     all remote plans before applying filters such as in
     ``tmt plans ls <name>``. This is **required** for the filtering to
     properly work with ``importing: become-parent`` option.
   ```

   *Feature with external documentation link* (PR #4367):
   ```yaml
   description: |
     Systemd `soft-reboot`__, a userspace-only reboot which does not reset
     kernel state, is now supported by tmt when supported by the
     guest: systemd must be in control, and boot ID must be available.
     tmt would use the ``systemctl soft-reboot`` command to trigger the
     reboot. Both ``tmt-reboot`` script and ``reboot`` phase support it,
     via ``tmt-reboot -s`` command and ``systemd-soft`` key, respectively.

     __ https://www.freedesktop.org/software/systemd/man/latest/systemd-soft-reboot.service.html
   ```

   *Plugin enhancement with spec references* (PR #4331-4332):
   ```yaml
   description: |
     The :ref:`/plugins/provision/beaker` plugin now supports
     :tmt:story:`device.device</spec/hardware/device>` and
     :tmt:story:`device.vendor</spec/hardware/device>` HW requirements.
   ```

   *Lint rule addition* (PR #4409):
   ```yaml
   description: |
     Introduced lint rule ``P009`` which checks if the step data is valid overall,
     which now covers failures due to data normalizations.
   ```

6. **Move pending entries**: Check if any release notes exist in `docs/releases/pending/` for PRs in this milestone:
   - Move matching fmf files to the release directory
   - Example: `git mv docs/releases/pending/1234.fmf docs/releases/1.65.0/1234.fmf`
   - This handles notes that were added during PR development

7. **Review**: Ensure all significant changes for the milestone are covered and the formatting matches the existing style in the `docs/releases/` directory.
