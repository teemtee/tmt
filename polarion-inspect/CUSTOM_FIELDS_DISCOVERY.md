# Polarion Custom Fields Discovery - RHELCockpit Project

## Summary

Discovered custom fields for "requirement" work items in the RHELCockpit Polarion project and tested their behavior.

## Custom Fields Found

Using `getCustomFieldKeys` service method, found **6 custom fields**:

1. ✅ **component** (lowercase) - TEXT - Works!
2. ❌ **Component** (capital C) - Exists but separate from lowercase version
3. ❌ **subsystemteam** - Unknown type - Silently fails to save
4. ✅ **tmtid** - TEXT - Works!
5. ⚠️  **jiraassignee** - TEXT - Not tested
6. ⚠️  **jirafixversion** - TEXT - Not tested

## Test Results

### Working Fields ✅

```yaml
extra-polarion-component: cockpit    # Saves successfully as text
extra-polarion-tmtid: /stories/install/minimal    # Saves successfully as text
```

### Non-Working Fields ❌

```yaml
extra-polarion-subsystemteam: rhel-cockpit    # Silently fails - value remains None
```

**Note:** `subsystemteam` might be an enum field that requires proper enum values from Polarion's configuration, but we couldn't retrieve the valid enum values via the API.

## Field Naming

**Important:** Custom field names in Polarion are case-sensitive!

- `component` (lowercase) ✅ - This works
- `Component` (capital C) ❌ - This is a different field

When using `extra-polarion-*` fields in FMF, hyphens are removed:
- `extra-polarion-subsystem-team` → `subsystemteam`
- `extra-polarion-component` → `component`

## API Methods Used

### Discovery
```python
# Get custom field keys
service.getCustomFieldKeys(work_item.uri)
# Returns: ['Component', 'component', 'jiraassignee', 'jirafixversion', 'subsystemteam', 'tmtid']

# Get custom field value
service.getCustomField(work_item.uri, 'component')
```

### Setting
```python
# Via pylero's _set_custom_field method
work_item._set_custom_field('component', 'cockpit')  # Works!
work_item._set_custom_field('tmtid', '/stories/install/minimal')  # Works!
work_item._set_custom_field('subsystemteam', 'rhel-cockpit')  # Silent fail
```

## Enum Field Issues

Attempted to query enum values using:
```python
service.getAllEnumOptionIdsForId('subsystemteam')
# Result: NullPointerException
```

This suggests either:
1. The field is not configured as an enum in Polarion
2. The API method doesn't work for custom enum fields
3. The field requires specific configuration we don't have access to

## Recommendations

### For Users

**Use only the working custom fields:**

```yaml
# In your story .fmf file
extra-polarion-component: your-component-name
extra-polarion-tmtid: /your/test/path
```

**Do NOT use** (until fixed):
```yaml
# extra-polarion-subsystemteam: value  # This won't work
```

### For Developers

To support `subsystemteam`:

1. **Check Polarion Configuration:**
   - Verify `subsystemteam` is properly configured for "requirement" work items
   - Check if it's an enum field and what values are valid
   - Verify write permissions for this field

2. **Alternative Approaches:**
   - Try setting via `EnumOptionId` if it's confirmed to be an enum
   - Check if field needs to be set via a different API method
   - Contact Polarion admin to verify field configuration

3. **API Limitations:**
   - `getAllEnumOptionIdsForId()` doesn't work for custom fields
   - No reliable way to discover custom enum values via pylero API
   - May need to configure valid values manually in code

## Files Modified

- `tmt/export/polarion.py` - Updated `set_polarion_custom_fields()` to use `_set_custom_field()` method
- `stories/install.fmf` - Updated to use correct field names (`component` not `casecomponent`)

## Current FMF Configuration

```yaml
/minimal:
    summary: Minimal tmt installation with core features only
    extra-polarion: RHELCOCKPIT-710
    extra-polarion-component: cockpit         # ✅ Works
    extra-polarion-tmtid: /stories/install/minimal  # ✅ Works
    # extra-polarion-subsystemteam: rhel-cockpit   # ❌ Doesn't work
```

## Verification

Check Polarion UI:
https://polarion.engineering.redhat.com/polarion/#/project/RHELCockpit/workitem?id=RHELCOCKPIT-710

Expected results:
- ✅ component = "cockpit"
- ✅ tmtid = "/stories/install/minimal"
- ❌ subsystemteam = (empty/not set)

