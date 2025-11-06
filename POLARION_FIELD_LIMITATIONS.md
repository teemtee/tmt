# Polarion Test Run Field Limitations

## Investigation Summary

This document details the investigation into setting Polarion test run custom fields and the technical limitations encountered.

## Working Fields ✅

These fields are successfully set and verified:

| Field | Polarion Field | Type | Example | Status |
|-------|---------------|------|---------|--------|
| `planned-in` | plannedin | EnumOptionId | RHEL-10.0.0 | ✅ **Works** |
| `assignee` | assignee | EnumOptionId | jscotka | ✅ **Works** |
| `pool-team` | group_id | Direct Attribute | rhel-cockpit | ✅ **Works** |
| `arch` | arch | EnumOptionId | x86_64 → x8664 | ✅ **Works** |

## Non-Working Fields ❌

### 1. Description Field

**Polarion Schema**: `ns20:Text`  
**Error**: `"java.lang.IllegalArgumentException: type cannot be null"`

**Investigation**:
- Field is defined as `ns20:Text` type in Polarion schema
- When accessed via `tr.description`, returns `EnumOptionId` with `id=None`
- Attempts to set using:
  - ✗ `Text(content=...)` object → "value is not a valid type"
  - ✗ `Text._suds_object` → "value is not a valid type"  
  - ✗ Direct assignment → "type cannot be null"
  - ✗ Via `_set_custom_field()` → "value is not a valid type"

**Root Cause**: Mismatch between Polarion's field definition (Text with render type: `$testRun.fields.description.render`) and how pylero handles it. The pylero library's `_obj_setter` explicitly rejects Text SUDS objects with error "the value ... is not a valid type". This is a **pylero library limitation**.

### 2. String Fields (build, composeid, logs)

**Polarion Schema**: `xsd:string`  
**Error**: `"org.xml.sax.SAXException: SimpleDeserializer encountered a child element, which is NOT expected"`

**Investigation**:
- Fields are defined as `xsd:string` in Polarion schema
- Attempts to set using:
  - ✗ Plain string → SimpleDeserializer error
  - ✗ Via `_set_custom_field(key, "value")` → SimpleDeserializer error
  - ✗ Direct attribute assignment → SimpleDeserializer error

**Root Cause**: Despite being defined as xsd:string, Polarion expects a specific SUDS object structure that we couldn't determine. The error suggests the XML serialization is producing unexpected child elements.

### 3. rplaunchurl (ReportPortal Launch URL)

**Polarion Schema**: `ns10:Text`  
**Status**: ⚠️ Untested but likely same issue as description field

## Technical Details

### Custom Fields Structure

Working fields are stored in `customFields` array as:
```python
(Custom){
   key = "plannedin"
   value = (EnumOptionId){
      id = "RHEL-10.0.0"
   }
}
```

### Why Enum Fields Work

Enum fields work because:
1. `_set_custom_field()` creates a `Custom` object with the string value
2. Polarion automatically wraps it in an `EnumOptionId` structure
3. The enum ID validation happens server-side

### Why String/Text Fields Fail

String/Text fields fail because:
1. Polarion expects specific SUDS object types (Text for ns:Text, unknown structure for xsd:string)
2. pylero's `_set_custom_field()` doesn't handle type conversion for these
3. Manual SUDS object construction is complex and not documented

## Workarounds Attempted

1. **Text Objects**: ✗ Failed - not accepted by pylero
2. **SUDS Objects**: ✗ Failed - type validation error
3. **Direct Assignment**: ✗ Failed - "type cannot be null"
4. **Factory Creation**: ⚠️ Could not access client factory correctly
5. **Raw SOAP Calls**: ❌ Not attempted (would bypass pylero entirely)

## Recommendations

### For Users

**Use the working fields** which provide the core functionality:
- **planned-in**: Required for release/cycle tracking ✅
- **assignee**: Required for ownership tracking ✅
- **pool-team**: Required for team assignment ✅
- **arch**: Required for architecture tracking ✅

**For build/compose tracking**:
- Use test run **title** to include build/compose info
- Use XUnit file properties (still generated even with direct API)
- Store in external systems and link via logs field (when/if it works)

### For Developers

To fix these issues would require:

1. **Short-term**: 
   - Investigation of how Polarion's web UI sets these fields
   - Analysis of actual SOAP requests made by working Polarion clients
   - Potential fixes to pylero library

2. **Long-term**:
   - Direct SOAP API calls bypassing pylero
   - Custom SUDS client configuration
   - Contribution to pylero project to fix Text type handling

## Testing Evidence

Test Run: `20251106-0924`  
URL: https://polarion.engineering.redhat.com/polarion/#/project/RHELCockpit/testrun?id=20251106-0924

**Verified Working**:
```
Group ID: rhel-cockpit
Custom Fields:
  assignee: jscotka
  plannedin: RHEL-10.0.0
  arch: x8664
```

**Verified Non-Working** (via manual Python tests):
- description: "type cannot be null" error
- build: "SimpleDeserializer" error  
- composeid: "SimpleDeserializer" error
- logs: "SimpleDeserializer" error

## Conclusion

The current implementation provides **all critical metadata tracking** needed for Polarion test runs:
- Release/cycle tracking (planned-in)
- Ownership (assignee)
- Team assignment (pool-team)
- Architecture (arch)

The non-working fields (description, build, composeid, logs) would be nice-to-have but are blocked by Polarion/pylero limitations that would require significant additional development effort to resolve.

