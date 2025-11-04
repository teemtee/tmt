# Polarion Story Export Example

This example demonstrates how to export tmt stories to Polarion as features.

## Story Structure

The `story.fmf` file contains a story that can be exported to Polarion:
- It will be created as a Polarion feature/requirement work item
- The `verified-by` links will be converted to "verifies" links to test cases in Polarion
- Story metadata (title, priority, tags, etc.) will be exported to corresponding Polarion fields

## Usage

### Export story to Polarion (dry run)

```bash
tmt stories export --how polarion --project-id YOUR_PROJECT --create --dry .
```

### Export story to Polarion (create feature)

```bash
tmt stories export --how polarion --project-id YOUR_PROJECT --create .
```

### Export story and link it back to fmf

```bash
tmt stories export --how polarion --project-id YOUR_PROJECT --create --link-polarion .
```

### Export with custom summary

```bash
tmt stories export --how polarion --project-id YOUR_PROJECT --append-summary --create .
```

## Features

### Story Export
- Stories are exported as Polarion "requirement" work items (features)
- All metadata fields are mapped to corresponding Polarion fields:
  - `summary` or `title` → Polarion title
  - `story` + `description` + `example` → Polarion description (**with Markdown to HTML conversion**)
  - `priority` → Polarion priority (must have=high, should have=medium, etc.)
  - `tag` → Polarion tags
  - `contact` → Polarion assignee
  - `enabled` → Polarion status (approved/inactive)

### Markdown Support
The `story`, `description`, and `example` fields support **Markdown formatting**, which is automatically converted to HTML for rich text display in Polarion:

- **Headers**: `# H1`, `## H2`, `### H3`
- **Bold**: `**text**` → **text**
- **Italic**: `_text_` → _text_
- **Lists**: Bullet (`-`) and numbered (`1.`) lists
- **Code blocks**: ` ```python ... ``` ` with syntax highlighting
- **Tables**: Full Markdown table syntax
- **Links**: `[text](url)`
- **Inline code**: `` `code` ``

Example:
```yaml
description: |
  # Feature Overview
  
  This feature provides **multi-provider authentication** with:
  
  ## Supported Providers
  1. **LDAP** - Enterprise directory
  2. **OAuth2** - Third-party auth
  
  | Provider | Status |
  |----------|--------|
  | LDAP     | ✓      |
  | OAuth2   | ✓      |
  
  See the configuration example:
  ```python
  config = {'providers': ['ldap', 'oauth2']}
  ```
```

### Verified-By Links and Automatic Test Export
- The `verified-by` links in stories are exported as "verifies" links in Polarion
- This creates "Linked Work Items" with the relationship: test case verifies requirement
- **New:** Test cases are automatically exported to Polarion if they don't exist (enabled by default)
- Supports:
  - Direct Polarion test case URLs
  - FMF test identifiers (automatically created in Polarion if needed)
  - FMF test paths (resolved and created in Polarion)

### Options
- `--project-id`: Specify the Polarion project
- `--polarion-feature-id`: Link to existing Polarion feature by work item ID
- `--create`: Create new features if they don't exist
- `--export-linked-tests` / `--no-export-linked-tests`: Automatically export test cases referenced in verified-by links (default: enabled)
- `--duplicate`: Allow creating duplicate features (default: prevent duplicates)
- `--link-polarion`: Add Polarion link back to the fmf metadata
- `--append-summary`: Include story summary in the Polarion title
- `--dry`: Dry run mode (no actual changes)

## Prerequisites

1. Install tmt with Polarion support:
   ```bash
   pip install tmt[export-polarion]
   ```

2. Configure Polarion credentials in `~/.pylero`:

   **Option A: Token Authentication (Recommended - More Secure)**
   ```ini
   [webservice]
   url=https://your-polarion-server/polarion
   svn_repo=https://your-polarion-server/repo
   default_project=YOUR_PROJECT
   disable_manual_auth=False
   token_enabled=True 
   user=USER_NAME
   token=your_personal_access_token
   ```
   
   To generate a personal access token in Polarion:
   - Log in to Polarion
   - Go to your user profile (top right corner)
   - Navigate to "Personal Access Tokens"
   - Create a new token with appropriate permissions
   - Copy the token and use it in the config file

   **Option B: Username/Password Authentication**
   ```ini
   [webservice]
   url=https://your-polarion-server/polarion
   svn_repo=https://your-polarion-server/repo
   default_project=YOUR_PROJECT
   user=your_username
   password=your_password
   ```

## Example Workflow

### First Time Export (Create New Feature with Tests)

1. Create your story in fmf format with `verified-by` links to test cases
2. Export to Polarion:
   ```bash
   tmt stories export --how polarion --project-id MYPROJECT --create --link-polarion .
   ```
3. The story will be created as a Polarion feature with:
   - All metadata properly mapped
   - **Automatic test case creation**: Referenced test cases will be created in Polarion
   - **Automatic linking**: Test cases will be linked with "verifies" relationship
   - A link back to the fmf source (if --link-polarion is used)
   - Polarion work item IDs stored in `extra-polarion` field

### Update Existing Feature

```bash
# Automatic detection (requires tmtid field in Polarion project)
tmt stories export --how polarion --project-id MYPROJECT .

# Or specify feature ID explicitly
tmt stories export --how polarion --project-id MYPROJECT --polarion-feature-id MYPROJECT-123 .
```

### Create Intentional Duplicate

```bash
# Use --duplicate flag to bypass duplicate prevention
tmt stories export --how polarion --project-id MYPROJECT --create --duplicate .
```

## Custom Polarion Fields

You can set custom Polarion fields directly from FMF metadata using the `extra-polarion-*` prefix:

```yaml
# Polarion custom fields
extra-polarion-team: rhel-cockpit
extra-polarion-planned-in:
  - rhel-10.2
  - rhel-9.8
extra-polarion-feature-type: enhancement
extra-polarion-target-release: 10.2
```

**Important:** Custom fields must be defined in Polarion before they can be set. If a field doesn't exist, you'll see a warning but the export will continue.

### Common Custom Fields

**For Stories:**
- `extra-polarion-team`: Team responsible
- `extra-polarion-planned-in`: Target releases (list)
- `extra-polarion-feature-type`: Type of feature
- `extra-polarion-target-release`: Primary target release
- `extra-polarion-epic`: Related epic ID

**For Tests:**
- `extra-polarion-test-type`: functional, integration, etc.
- `extra-polarion-automation-level`: automated, manual
- `extra-polarion-risk-level`: low, medium, high

See `POLARION_CUSTOM_FIELDS.md` for complete documentation.

## Notes

- The export will look for existing Polarion work items using the tmt UUID or `extra-polarion` field
- **New:** Test cases are automatically exported and linked when exporting stories (can be disabled with `--no-export-linked-tests`)
- The Polarion work item IDs are stored in the `extra-polarion` field in FMF metadata for future reference
- Test cases are created with the relationship "verifies" to the story/requirement
- Custom Polarion fields can be set using `extra-polarion-*` metadata


