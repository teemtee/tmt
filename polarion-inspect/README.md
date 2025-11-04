# Polarion Integration - Inspection Tools

Diagnostic scripts for inspecting and debugging Polarion integration via the `pylero` library.

## Quick Start

All scripts connect to Polarion using your `~/.pylero` configuration. Run them from this directory:

```bash
cd polarion-inspect

# Verify custom fields are set correctly
python3 verify_custom_fields.py

# Discover what custom fields exist
python3 discover_custom_fields.py

# List all available Polarion API methods
python3 list_polarion_service_methods.py

# Inspect work item structure
python3 inspect_polarion_fields_v2.py

# Deep inspection of SUDS object
python3 check_work_item_suds.py
```

## Available Scripts

### 🔍 verify_custom_fields.py
**Purpose:** Verify custom fields were saved to Polarion  
**Usage:** Run after exporting a story to check if custom fields are set  
**Example:**
```bash
python3 verify_custom_fields.py
# Output shows which custom fields have values
```

### 📋 discover_custom_fields.py
**Purpose:** Discover what custom fields exist in a Polarion project  
**Usage:** Find out what fields are available for requirement work items  
**Key Info:** Discovers field names and attempts to determine types

### 🔧 list_polarion_service_methods.py
**Purpose:** List all 188 available SOAP service methods  
**Usage:** Understand what API operations are available  
**Categories:** Lists enum-related, field-related, and work item methods

### 🔬 inspect_polarion_fields_v2.py
**Purpose:** Inspect work item attributes and types  
**Usage:** See all fields available on a work item and their current values  
**Output:** Shows standard fields, custom fields, and enum fields

### 🧪 check_work_item_suds.py
**Purpose:** Deep inspection of SUDS object structure  
**Usage:** Low-level investigation of work item internal structure  
**Advanced:** Use when debugging field access issues

## Custom Fields in RHELCockpit Project

Based on API inspection, the following custom fields are available for "requirement" work items:

| Field Name | Type | Status | Usage |
|------------|------|---------|-------|
| `component` | TEXT | ✅ **Works** | `extra-polarion-component: cockpit` |
| `tmtid` | TEXT | ✅ **Works** | `extra-polarion-tmtid: /stories/install/minimal` |
| `subsystemteam` | Unknown | ❌ Fails | Silently fails to save (needs admin config) |
| `Component` | Unknown | ⚠️  Untested | Note: Capital C - separate from `component` |
| `jiraassignee` | TEXT | ⚠️  Untested | JIRA integration field |
| `jirafixversion` | TEXT | ⚠️  Untested | JIRA integration field |

### Working Configuration Example

```yaml
# stories/example.fmf
/feature:
    summary: My Feature
    extra-polarion: RHELCOCKPIT-123
    extra-polarion-component: cockpit              # ✅ Works
    extra-polarion-tmtid: /stories/example/feature # ✅ Works
```

## Polarion Story Export Features

### CLI Options

```bash
tmt stories export --how polarion [OPTIONS] STORY_NAME
```

**Required:**
- `--project-id PROJECT_ID` - Polarion project (e.g., RHELCockpit)

**Optional:**
- `--create` - Create new work items if they don't exist
- `--polarion-feature-id ID` - Link to existing Polarion feature
- `--duplicate / --no-duplicate` - Allow/prevent duplicates (default: no-duplicate)
- `--export-linked-tests / --no-export-linked-tests` - Auto-export test cases (default: true)
- `--link-polarion` - Add Polarion URL back-references to FMF
- `--append-summary` - Include test links in story description

### Key Features

1. **Duplicate Prevention:** Automatically searches for existing features using `tmtid` or `extra-polarion` field
2. **Test Case Linking:** Exports `verified-by` test cases and links them with "verifies" relationship
3. **Custom Fields:** Supports setting Polarion custom fields via `extra-polarion-*` metadata
4. **Fallback Storage:** If `tmtid` field unavailable, stores Polarion ID in `extra-polarion` FMF field
5. **Canonical URLs:** Generates proper URLs to test scripts (not metadata files) in upstream repo

### Example Usage

```bash
# Export story with test cases
tmt stories export --how polarion --project-id RHELCockpit --create /stories/install/minimal

# Update existing feature
tmt stories export --how polarion --project-id RHELCockpit --polarion-feature-id RHELCOCKPIT-710 /stories/install/minimal

# Allow creating duplicate
tmt stories export --how polarion --project-id RHELCockpit --create --duplicate /stories/install/minimal
```

## FMF Metadata Reference

### Story Configuration

```yaml
/feature:
    summary: Feature Title
    description: Detailed description
    
    # Polarion integration
    extra-polarion: RHELCOCKPIT-123           # Polarion work item ID
    extra-polarion-component: cockpit         # Custom field: component
    extra-polarion-tmtid: /stories/feature    # Custom field: tmtid
    
    # Link test cases
    link:
      - verified-by: /tests/integration/basic
      - verified-by: /tests/unit/smoke
```

### Verified-by Links

Test cases in `verified-by` links are:
- Automatically exported to Polarion (if they don't exist)
- Linked to the story with "verifies" relationship
- Displayed in Polarion UI under "Linked Work Items"

## Troubleshooting

### Custom Fields Not Saving

**Problem:** Custom field set successfully but value is None when queried  
**Possible Causes:**
1. Field requires enum value but you're setting text
2. Field is read-only or requires special permissions
3. Field not enabled for "requirement" work item type

**Solution:** Contact Polarion admin to verify field configuration

### tmtid Field Issues

**Problem:** Warning: "Can't add ID because project doesn't have 'tmtid' field defined"  
**Automatic Fallback:** tmt stores Polarion ID in `extra-polarion` field instead  
**Permanent Fix:** Enable `tmtid` custom field for requirement work item type in Polarion admin

### Duplicate Features Created

**Problem:** Same story exported multiple times creates duplicate features  
**Solution:** Use `--no-duplicate` flag (default behavior) or set `extra-polarion` field in FMF

## API Methods Reference

The Polarion SOAP API provides 188 methods. Key methods used by tmt:

**Work Item Management:**
- `createWorkItem` - Create new work items
- `updateWorkItem` - Update existing work items
- `getWorkItemById` - Retrieve work item by ID
- `queryWorkItems` - Query work items (used for duplicate detection)

**Custom Fields:**
- `getCustomFieldKeys` - Get available custom field names
- `getCustomField` - Read custom field value
- `setCustomField` - Set custom field value (via CustomField object)

**Linking:**
- `addLinkedItem` - Link work items (used for verified-by relationships)
- `getBackLinkedWorkitems` - Get reverse links

**Enums:**
- `getAllEnumOptionIdsForId` - Get enum values (doesn't work for custom fields)

## Development Notes

- All scripts use `RHELCOCKPIT-710` as default test work item
- Custom field API (`getCustomFieldKeys`, `setCustomField`) uses CustomField objects
- Enum queries via `getAllEnumOptionIdsForId` return NullPointerException for custom fields
- Field names are case-sensitive: `component` ≠ `Component`
- Hyphenated FMF field names map to concatenated Polarion names: `subsystem-team` → `subsystemteam`

## Files

- `CUSTOM_FIELDS_DISCOVERY.md` - Detailed analysis of custom fields investigation

## Related Implementation

- Main code: `/tmt/export/polarion.py`
- CLI interface: `/tmt/cli/_root.py`
- Example: `/examples/polarion-story/`
- Test story: `/stories/install.fmf`
