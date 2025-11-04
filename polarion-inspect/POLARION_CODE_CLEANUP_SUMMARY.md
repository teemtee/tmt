# Polarion Code Cleanup Summary

## Overview

Cleaned up Polarion story export code to improve maintainability, remove unnecessary complexity, and use proper logging instead of excessive `echo()` output.

## Changes Made

### 1. CLI Options Cleanup (`tmt/cli/_root.py`)

**Removed:**
- `--debug` flag (unused parameter, never referenced in code)
- Custom `--dry` option (replaced with standard `@dry_options`)

**Replaced:**
- Custom dry/debug flags → Standard tmt `@dry_options` and `@verbosity_options` decorators

**Result:** Better integration with tmt's standard verbosity mechanism

### 2. Logging Improvements (`tmt/export/polarion.py`)

**Before:** 40+ `echo(style(...))` statements that always printed regardless of verbosity level

**After:** Proper logger usage with appropriate levels:
- `logger.info()` - Important user-facing progress (e.g., "Setting custom fields", "Linking test cases")
- `logger.debug()` - Detailed field-by-field updates (e.g., "title: ...", "priority: ...")
- `logger.warning()` - Issues that don't stop execution (e.g., "Could not set field", "Test not found")
- `echo()` - Only final success message (user-facing result)

**Benefits:**
- Respects tmt's `-v/--verbose` and `-d/--debug` flags
- Less noise in normal output
- Easier to debug with `-vv` when needed

### 3. Exception Handling Cleanup

**Removed Ambiguous Fallbacks:**

#### a) PolarionRequirement Import
```python
# BEFORE - Creates different behavior depending on pylero version
try:
    from pylero.work_item import Requirement as PolarionRequirement
except ImportError:
    PolarionRequirement = PolarionWorkItem  # Ambiguous fallback

# AFTER - Clear, consistent behavior
PolarionRequirement = PolarionWorkItem  # Always use WorkItem
```

#### b) convert_to_polarion_enum Function
```python
# BEFORE - Caught ALL exceptions, returned original value on any error
try:
    # ... conversion logic ...
except (ImportError, Exception) as exc:  # Too broad!
    return value  # Ambiguous: did it work or not?

# AFTER - Removed entirely (unused function)
```

#### c) Custom Field Setting
```python
# BEFORE - Tried enum first, fell back to text silently
try:
    polarion_item._set_custom_field(field_name, EnumOptionId(...))
except Exception:  # Too broad!
    try:
        polarion_item._set_custom_field(field_name, str(value))
    except Exception:  # Also too broad!
        pass

# AFTER - Single, clear path
try:
    polarion_item._set_custom_field(field_name, str(value))
except (AttributeError, PolarionException) as exc:  # Specific errors only
    log.debug(f"Failed to set field: {exc}")
    fields_failed.append((field_name, str(exc)))
```

### 4. Code Removal

**Deleted:**
- `convert_to_polarion_enum()` function (40 lines) - Unused after simplification
- Unused `enum_fields` set
- Multiple redundant try/except blocks
- Debugging echo statements throughout

**Simplified:**
- Custom field setting logic (removed enum/text fallback complexity)
- Import logic (removed conditional Requirement import)

### 5. Test File Reverts

**Reverted changes to:**
- `stories/install.fmf` - Removed testing additions (`extra-polarion-*` fields, extra links)
- `tests/link/basic/main.fmf` - Removed testing additions (`extra-polarion`, `id`)

**Reason:** These were only for development/testing, not part of the feature

## Statistics

```
 stories/install.fmf       |   9 +-    (reverted to original)
 tests/link/basic/main.fmf |   7 +-    (reverted to original)
 tmt/cli/_root.py          |  16 +--    (removed custom options)
 tmt/export/polarion.py    | 311 ++--    (major cleanup)
 4 files changed, 97 insertions(+), 246 deletions(-)
```

**Net reduction:** 149 lines removed

## Code Quality Improvements

### Before
- ❌ 40+ always-visible echo statements
- ❌ Unused `--debug` parameter
- ❌ Broad `except Exception` catches
- ❌ Ambiguous fallback behaviors
- ❌ Unused functions (convert_to_polarion_enum)

### After
- ✅ Proper logger with verbosity levels
- ✅ Standard tmt options (`@dry_options`, `@verbosity_options`)
- ✅ Specific exception handling
- ✅ Clear, single-path execution
- ✅ Removed all unused code

## Functionality Preserved

**All features still work:**
- ✅ Story export to Polarion
- ✅ Test case auto-export
- ✅ Custom field setting
- ✅ Duplicate prevention
- ✅ Link management
- ✅ Dry-run mode

**User experience improved:**
- Normal output is clean and concise
- Verbose mode (`-v`) shows progress
- Debug mode (`-vv`) shows all details
- Error messages are clearer

## Testing

Example of improved output:

```bash
# Normal mode - clean output
$ tmt stories export --how polarion --project-id RHELCockpit --create /stories/feature
Story 'My Feature' successfully exported to Polarion.

# Verbose mode - see progress
$ tmt -v stories export --how polarion --project-id RHELCockpit --create /stories/feature
Setting custom Polarion fields
Exporting linked test cases to Polarion
Creating test case /tests/basic in Polarion
Test case exported: RHELCOCKPIT-123
Linking test cases to feature
Linked: RHELCOCKPIT-123 (verifies)
Story 'My Feature' successfully exported to Polarion.

# Debug mode - see everything
$ tmt -vv stories export --how polarion --project-id RHELCockpit --create /stories/feature
title: My Feature
description: As a user...
priority: high
tags: feature fmf-export
assignee: user
enabled: True
Setting custom Polarion fields
Set 2 custom field(s): component, tmtid
...
```

## Remaining Optional Exception Handlers

These are intentionally kept because the fields are optional:

```python
# Priority - optional field, don't fail if it doesn't exist
try:
    polarion_feature.priority = mapped_priority
except (AttributeError, PolarionException) as exc:
    logger.debug(f"Failed to set priority: {exc}")

# Tags - optional field
try:
    polarion_feature.tags = ' '.join(story.tag)
except (AttributeError, PolarionException) as exc:
    logger.debug(f"Failed to set tags: {exc}")

# Status - optional field
try:
    polarion_feature.status = 'approved'
except (AttributeError, PolarionException) as exc:
    logger.debug(f"Failed to set status: {exc}")
```

These are correct - they allow the export to continue even if optional fields can't be set.

## Files for Examples

All Polarion integration examples remain in:
- `examples/polarion-story/` - Complete working example
- `polarion-inspect/` - Diagnostic scripts and documentation

