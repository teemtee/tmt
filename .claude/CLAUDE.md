# tmt AI Instructions

This file contains instructions for AI assistants (Claude Code, Gemini CLI, GitHub Copilot, etc.) when working with the tmt codebase. Different sections cover different tasks.

## Release Notes Generation

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

   **Example** (from PR #4307):
   ```yaml
   description: |
     The :ref:`prepare shell</plugins/prepare/shell>` and
     :ref:`finish shell</plugins/finish/shell>` plugins now produce results in the
     ``results.yaml`` file of the step.
   ```

6. **Move pending entries**: Check if any release notes exist in `docs/releases/pending/` for PRs in this milestone:
   - Move matching fmf files to the release directory
   - Example: `git mv docs/releases/pending/1234.fmf docs/releases/1.65.0/1234.fmf`
   - This handles notes that were added during PR development

7. **Review**: Ensure all significant changes for the milestone are covered and the formatting matches the existing style in the `docs/releases/` directory.

## Using This Instruction with Different AI Tools

### Claude Code

The `.claude/CLAUDE.md` file is automatically loaded when running Claude Code in this repository.

### Gemini CLI

Use this instruction file as a system instruction:

```bash
gemini --system-instruction "$(cat .claude/CLAUDE.md)"
```

### GitHub Copilot CLI

Reference these instructions in your prompt:

```bash
gh copilot suggest "Using the guidelines in .claude/CLAUDE.md, generate release notes for milestone 1.65"
```

Or use `gh copilot explain` for understanding existing code:

```bash
gh copilot explain "Explain the release notes structure described in .claude/CLAUDE.md"
```

### Other AI CLI Tools

For any other AI CLI tool, just use a prompt like:

```
Using the guidelines in .claude/CLAUDE.md, generate release notes for milestone 1.65
```

Adjust according to the instructions you are interested in.

## GitHub MCP Server Setup

The GitHub MCP (Model Context Protocol) server provides enhanced GitHub integration for AI CLI agents, enabling direct interaction with GitHub APIs for searching PRs, reading issues, and browsing repository contents.

> **Note**: Examples below use `podman`, but you can substitute `docker` if that's what you have installed.

### Required Token Scopes

Create a GitHub Personal Access Token at https://github.com/settings/tokens with these scopes:

| Scope | Description |
|-------|-------------|
| `repo` | Full control of private repositories |
| `public_repo` | Access public repositories only (alternative to `repo`) |
| `read:org` | Read organization membership |
| `read:project` | Read access to projects |

For read-only access to public repositories, `public_repo`, `read:org`, and `read:project` are sufficient.

### Claude Code

```bash
claude mcp add github -- podman run -e GITHUB_PERSONAL_ACCESS_TOKEN=<your-token> --rm -i ghcr.io/github/github-mcp-server
```

Verify with:

```bash
claude mcp list
```

### Gemini CLI

Add to your `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "github": {
      "command": "podman",
      "args": ["run", "--rm", "-i", "ghcr.io/github/github-mcp-server"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "$GITHUB_TOKEN"
      }
    }
  }
}
```

Set the `GITHUB_TOKEN` environment variable with your personal access token.

## Adding Custom Instructions

This file contains project-wide instructions for all contributors. For personal or additional use cases:

### Claude Code

- **Personal global instructions**: Add to `~/.claude/CLAUDE.md` for instructions that apply to all your projects
- **Project-specific additions**: You can add additional sections to this file via PR for team-wide instructions

### Gemini CLI

- Use multiple `--system-instruction` flags or combine instruction files
- Personal instructions can go in `~/.gemini/GEMINI.md` and be loaded alongside project instructions

### General Pattern

For any AI tool, you can typically:
1. Create a personal instruction file (e.g., `~/.config/<tool>/instructions.md`)
2. Reference it alongside project instructions in your prompts
3. Submit PRs to add new sections to this file for shared team instructions
