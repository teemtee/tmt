# Polarion + ReportPortal Integration Example

This example demonstrates the integrated workflow for reporting test results to both ReportPortal and Polarion using TMT's token-based upload feature, with comprehensive field usage and schema validation.

## Overview

The plan shows all available Polarion report options including:
- **Custom fields**: planned-in, assignee, pool-team, arch, platform, sample-image, browser (chromium), component (cockpit)
  - Note: Some fields like build, compose-id, logs have API limitations (see Field Compatibility section)
- **Context dimensions**: deployment-mode (automatically included in Polarion report)
- **Schema validation**: Field type checking and enum validation
- **Value transformation**: Automatic conversion (e.g., x86_64 → x8664)
- **Auto-create**: Automatically create missing test cases
- **Rich metadata**: Custom titles, descriptions, and metadata

The plan is configured to:

1. **Upload to ReportPortal**: Full test results with detailed logs and traces
2. **Create Polarion Test Run**: Metadata, test records, and link to ReportPortal launch
3. **Link Systems**: Polarion test run includes ReportPortal launch URL in `rplaunchurl` field

## Features Demonstrated

- ✅ **Token-based authentication** for Polarion uploads (supports API tokens)
- ✅ **ReportPortal integration** with launch URL linking in `rplaunchurl` field
- ✅ **Schema-driven custom fields** (configured via plan file, no CLI options needed):
  - planned-in (test cycle/release)
  - assignee (responsible person)
  - pool-team (team/subsystem)
  - arch (architecture with auto-normalization)
  - build (build number)
  - compose-id (compose identifier)
  - platform (execution platform)
  - sample-image (image used)
  - logs (artifacts URL)
  - browser (browser used for testing)
  - component (component under test)
  - fips (FIPS mode flag)
  - selinux-state, selinux-mode, selinux-policy
  - deployment-mode (from FMF context)
  - schedule-task
- ✅ **Schema validation**: Validates field types and enum values automatically
- ✅ **Value transformation**: x86_64 → x8664 via schema mappings
- ✅ **Auto-generated title**: `[polarion ID] - [distro] - [plan name]` (can be overridden)
- ✅ **Auto-generated description**: From plan's summary and description with HTML formatting (can be overridden)
- ✅ **Enhanced descriptions** with plan summary, description, environment, and provision details
- ✅ **Auto-create missing test cases** in Polarion
- ✅ **Generic provision data display** (works with testcloud, beaker, artemis, etc.)
- ✅ **XML sanitization** to handle invalid characters

### Custom Fields: Plan-Only Configuration

**Important**: Custom Polarion fields (like `planned-in`, `assignee`, `arch`, etc.) are **only configurable via TMT plan files**. They do not have command-line options to keep the CLI simple and uncluttered.

**Core CLI Options** (available via command-line):
- `--project-id` - Polarion project ID
- `--title` - Test run title  
- `--description` - Test run description
- `--template` - Test run template
- `--token-upload` - Use direct API with token auth
- `--auto-create-testcases` - Auto-create missing test cases
- `--schema` - Path to custom schema file
- `--file` - Output XML file path
- `--upload` / `--no-upload` - Enable/disable upload
- `--prettify` / `--no-prettify` - Format XML output
- `--include-output-log` - Include test output in XML

**All Custom Fields** must be configured in your plan file as shown in the examples below.

## Configuration

The plan uses two report steps in sequence, demonstrating all available Polarion fields:

```yaml
# FMF context dimensions (automatically added to Polarion report)
context:
    deployment-mode: package

report:
    # Step 1: ReportPortal
    - how: reportportal
      project: cockpit
      suite-per-plan: true
      url: https://reportportal-cockpit.apps.dno.ocp-hub.prod.psi.redhat.com
      token: your_token_here
      upload: false  # Set to true when you have valid credentials
    
    # Step 2: Polarion with comprehensive fields
    - how: polarion
      # Project and authentication
      project-id: RHELCockpit
      token-upload: true                           # Use direct API for token auth
      
      # Test run metadata (optional - auto-generated if not specified)
      # title: Custom Title Here                   # If omitted: "[polarion ID] - [distro] - [plan name]"
      # description: Custom description            # If omitted: auto-generated from plan's summary and description
      template: Empty                               # Test run template (optional)
      
      # Test case management
      auto-create-testcases: true                   # Auto-create missing test cases
      
      # Custom fields (validated by schema)
      planned-in: RHEL-10.0.0                       # Test cycle/release
      assignee: jscotka                             # Responsible person
      pool-team: rhel-cockpit                       # Team/subsystem
      arch: x86_64                                  # Architecture (→ x8664)
      
      # Additional metadata fields
      # Note: Some string fields may cause SimpleDeserializer errors depending on
      # your Polarion configuration. Enum fields are more reliable.
      # build: RHEL-10.0.0-20250113.0                 # Build number (string - may fail)
      # compose-id: RHEL-10.0.0-20250113.0            # Compose ID (string - may fail)
      platform: beaker                              # Platform
      sample-image: rhel-10-guest-image.qcow2       # Image used
      # logs: https://artifacts.example.com/12345     # Logs URL (string - may fail)
      
      # Test-specific custom fields
      browser: chromium                             # Browser used
      component: cockpit                            # Component under test (multi-select)
      
      fips: false                                   # FIPS mode
      
      # File and upload control
      file: xunit.xml                               # Output filename
      upload: false                                 # Set to true for actual upload
      prettify: true                                # Format XML nicely
      include-output-log: true                      # Include full test output
```

## Field Compatibility

### Working Fields

Based on testing with Polarion ALM, the following field types are **reliably supported**:

- ✅ **Enum fields** (single-select): plannedin, assignee, pool-team, arch, browser
- ✅ **Enum fields** (multi-select): component
- ✅ **String fields**: platform, sample-image
- ✅ **Boolean fields**: fips
- ✅ **Rich text fields**: description, rplaunchurl

### Fields with Known Issues

Some **string-type fields** may cause `SimpleDeserializer` errors in certain Polarion configurations:

- ⚠️ **build**: May not be configured for direct API setting
- ⚠️ **compose-id**: May not be configured for direct API setting
- ⚠️ **logs**: May not be configured for direct API setting

### Multi-Select Enum Fields

Multi-select enum fields (like `component`) are now **fully supported**! ✅

**How It Works:**
Instead of using `_set_custom_field()` (which expects suds objects), the code now uses the property setter directly:
```python
test_run.component = ['cockpit']  # Set via property setter
```

The property setter (`_custom_setter`) has special handling for array fields with `enum_id` that:
1. Creates the appropriate `ArrayOfEnumOptionId` suds object
2. For each value in the list, creates proper `EnumOptionId` objects using `_cls_inner()`
3. Appends them to the custom fields array

**Previous Approaches That Failed:**
- ❌ Using `_set_custom_field()` with string lists
- ❌ Using `_set_custom_field()` with EnumOptionId objects

**Key Fix:**
Avoiding `hasattr()` which triggers the property getter and fails on uninitialized fields. Instead, checking `TestRun._cls_suds_map` to verify field existence.

### How It Works

The code now:
1. Checks schema for `read_only` property
2. Attempts to set each field individually
3. Updates after each field to detect failures early
4. On failure, warns and reloads test run to continue with remaining fields

This ensures maximum compatibility while still attempting to set all configured fields.

## Auto-Generated Fields

### Title

If not specified, the title is **auto-generated** using the format:

```
[polarion ID] - [distro] - [plan name]
```

**Example**: `20250113-1425 - RHEL-9.8 - /examples/polarion-run-report/plan`

- **Polarion ID**: Timestamp in format `YYYYMMDD-HHMM`
- **Distro**: Extracted from provision facts or image name (e.g., `RHEL-9.8`, `Fedora-42`)
- **Plan Name**: Full FMF plan name

**Override**: Set `title: Custom Title` in the report configuration to use a custom title instead.

### Description

If not specified, the description is **auto-generated** from:

1. **Plan Summary**: The plan's `summary` field
2. **Plan Description**: The plan's `description` field (formatted as HTML)
3. **Environment Variables**: From plan's `environment` section
4. **Provision Details**: Hardware, image, distro, kernel, etc.
5. **ReportPortal Link**: Link to ReportPortal launch (if available)

**Override**: Set `description: Custom description` in the report configuration to use a custom description instead.

### Example: Using Custom Title and Description

If you want to override the auto-generated fields:

```yaml
report:
    - how: polarion
      project-id: RHELCockpit
      token-upload: true
      
      # Override auto-generated title
      title: "Feature XYZ Validation - Build 12345"
      
      # Override auto-generated description
      description: |
        Custom test run for Feature XYZ.
        
        Build: RHEL-10.0.0-20250113.0
        Jenkins: https://jenkins.example.com/job/xyz/42
      
      # ... other fields
```

## Running the Example

### Prerequisites

1. **ReportPortal**: URL and token configured (or set `upload: false`)
2. **Polarion**: Token configured in `~/.pylero` (or set `upload: false`)
3. **Test ID**: Test has an `id` field (UUID) for Polarion matching

### Execute

```bash
# Run the example plan
cd examples/polarion-run-report
tmt run --all provision --how local --feeling-safe

# Or specify the plan directly
tmt run --all plan --name /examples/polarion-run-report/plan \
    provision --how local --feeling-safe
```

### Expected Output

```
discover
    Found 1 test: /test

execute
    pass /test (on default-0)

report (reportportal)
    url https://reportportal-cockpit.../launches/75
    
report (polarion)
    xUnit file saved at: /tmp/tmt-test/plan/report/default-1/xunit.xml
    Polarion upload can be done manually using command:
    curl -k -u <USER>:<PASSWORD> -X POST -F file=@<XUNIT_XML_FILE_PATH> ...

total: 1 test passed
```

## Generated Files

### xUnit File (Polarion)

The generated `xunit.xml` is always created for reference and manual uploads:

- **Test results**: Pass/fail status with execution time
- **Test output**: Full standard output from test execution
- **Metadata properties**:
  - `polarion-custom-arch`: x8664 (normalized from x86_64)
  - `polarion-custom-assignee`: jscotka
  - `polarion-custom-plannedin`: RHEL-10.0.0
  - `polarion-custom-poolteam`: rhel-cockpit
  - `polarion-custom-build`: RHEL-10.0.0-20250113.0
  - `polarion-custom-composeid`: RHEL-10.0.0-20250113.0
  - `polarion-custom-platform`: beaker
  - `polarion-custom-browser`: chromium
  - `polarion-custom-component`: cockpit-storage
  - `polarion-custom-deploymentMode`: package (from FMF context)
  - `polarion-testrun-template-id`: Empty
  - `polarion-testcase-id`: Test case work item ID
  - `polarion-testcase-project-id`: RHELCockpit

**Note**: When `token-upload: true`, the xUnit file is still generated but the upload uses the Polarion API directly, which supports richer descriptions and metadata.

### ReportPortal Launch

When `upload: true`, ReportPortal creates:

- Launch with plan name
- Suite structure (if `suite-per-plan: true`)
- Test items with detailed logs
- Launch URL saved to file for Polarion integration

## Workflow Details

### 1. ReportPortal Upload

The first report step uploads to ReportPortal:
- Full test output and logs
- Stack traces and screenshots (if any)
- Test hierarchy (with `suite-per-plan`)
- Returns launch URL

### 2. Polarion Test Run Creation

The second report step:
- Detects the ReportPortal launch URL (from saved file)
- Creates Polarion test run with metadata:
  - **Title**: Auto-generated as `[polarion ID] - [distro] - [plan name]` (unless overridden)
    - Example: `20251113-1425 - RHEL-9.8 - /examples/polarion-run-report/plan`
  - **Description**: Auto-generated from plan (unless overridden) including:
    - TMT plan summary
    - TMT plan description (formatted as HTML)
    - Environment variables
    - Provision details (method, image, memory, disk, addresses, distro, kernel, etc.)
    - ReportPortal launch link
  - **Metadata**: planned-in, assignee, pool-team, arch (normalized), build, compose-id, platform, browser, component, etc.
  - **rplaunchurl** field → ReportPortal launch URL
- Adds test records for each result

### 3. Token-Based Upload

With `token-upload: true`:
- Uses Polarion's direct API instead of XUnit importer
- Supports both token and password authentication
- Provides rich descriptions with HTML formatting
- Sets ReportPortal launch URL in custom field
- Auto-creates missing test cases (with `auto-create-testcases`)

### 4. Generic Provision Data Display

The Polarion description includes whatever provision data is available:

**Testcloud/Virtual**:
- Method, Image, Image URL, Memory, Disk, Name, Key, Primary Address, Port, Arch, Distro, Kernel

**Beaker**:
- Method, Image, Compose, Pool, Memory, Disk, Arch, Distro, Kernel

**Artemis**:
- Method, Image, Pool, API URL, Memory, Disk, Arch, Distro, Kernel

This generic approach works with any provision method and automatically displays all available metadata without special handling.

## Troubleshooting

### Test not found in Polarion

The test needs to have a Polarion work item with matching `tmtid`:

```bash
# Export test to Polarion first
tmt tests export --how polarion --project-id RHELCockpit

# Or use auto-create feature
# (add to plan.fmf: auto-create-testcases: true)
```

### "The 'local' provision plugin requires '--feeling-safe' option"

Add `--feeling-safe` to provision step:

```bash
tmt run --all provision --how local --feeling-safe
```

### ReportPortal URL not appearing in Polarion

Check that:
1. ReportPortal report step runs before Polarion
2. ReportPortal upload succeeds (`upload: true`)
3. Polarion has `rplaunchurl` custom field defined
4. Using `token-upload: true` (required for setting custom fields)

### SAXParseException or XML parsing errors

The reporter automatically sanitizes invalid XML characters (like null bytes `0x0`) from:
- Test run title
- Test run description
- Test case notes
- Test output logs

This ensures compatibility with Polarion's XML parser even when test outputs contain binary data or control characters.

## Testing Without Credentials

Set `upload: false` for both reporters to test locally without uploading:

```yaml
report:
    - how: reportportal
      upload: false  # Generate launch locally only
      # ... other config
    
    - how: polarion
      upload: false  # Generate xUnit file only
      # ... other config
```

This generates all files without requiring valid credentials.

## Dynamic Schema

**Schema generation**:

The Polarion reporter automatically queries your Polarion project at runtime to 
discover available custom fields and their types. The generated schema is saved 
to the TMT output directory (alongside xunit.xml) for reference.

```yaml
report:
    - how: polarion
      project-id: RHELCockpit  # Schema will be generated from this project
```

The schema file will be saved at:
```
/var/tmp/tmt/run-XXX/plan-name/report/default-1/polarion-schema.yaml
```

## See Also

- **Polarion reporter docs**: `tmt run report --how polarion --help`
- **ReportPortal reporter docs**: `tmt run report --how reportportal --help`
- **Dynamic schema**: Generated at `<workdir>/report/default-1/polarion-schema.yaml`
- **Main integration guide**: `examples/polarion-reportportal-README.md`

