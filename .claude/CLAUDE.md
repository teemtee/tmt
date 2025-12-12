# tmt Release Notes Generator

## Instructions

When creating release notes for tmt, use the milestone name as input (e.g., "1.59") and follow these guidelines:

1. **Search for PRs**: Go through all pull requests for the specified milestone (e.g., milestone:1.59)

2. **Check existing entries**: Review the content of `docs/releases.rst` to understand the format and avoid duplicating entries that are already present

3. **Format requirements**:
   - Keep strictly to the existing format in `docs/releases.rst`
   - Be concise but descriptive
   - Skip PRs that already have release notes added
   - Focus on user-facing changes and improvements

4. **Content guidelines**:
   - Include new features and enhancements
   - Document bug fixes that affect user experience
   - Mention API changes or deprecations
   - Note any breaking changes
   - Include plugin improvements and new capabilities

5. **Structure**: Follow the pattern shown in the releases file:
   ```
   tmt-X.XX.X
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

   [Description of changes, organized by feature/area]
   ```

6. **Review**: Ensure all significant changes for the milestone are covered and the formatting matches the existing style in the releases file.
