# Polarion + ReportPortal Integration Example

This example demonstrates the integrated workflow for reporting test results to both ReportPortal and Polarion using TMT's token-based upload feature.

## Overview

The plan is configured to:

1. **Upload to ReportPortal**: Full test results with detailed logs and traces
2. **Create Polarion Test Run**: Metadata, test records, and link to ReportPortal launch
3. **Link Systems**: Polarion test run includes ReportPortal launch URL in `rplaunchurl` field

## Features Demonstrated

- ✅ Token-based authentication for Polarion uploads
- ✅ ReportPortal integration with launch URL linking
- ✅ Rich metadata fields (planned-in, assignee, pool-team, arch)
- ✅ Enhanced descriptions with plan summary, description, environment, and provision details
- ✅ Smart title generation: `[polarion ID] - [distro] - [plan name]`
- ✅ Auto-create missing test cases in Polarion
- ✅ Architecture normalization (x86_64 → x8664)
- ✅ Generic provision data display (works with testcloud, beaker, artemis, etc.)
- ✅ XML sanitization to handle invalid characters

## Configuration

The plan uses two report steps in sequence:

```yaml
report:
    # Step 1: ReportPortal
    - how: reportportal
      project: cockpit
      suite-per-plan: true
      url: https://reportportal-cockpit.apps.dno.ocp-hub.prod.psi.redhat.com
      token: your_token_here
      upload: false  # Set to true when you have valid credentials
    
    # Step 2: Polarion
    - how: polarion
      project-id: RHELCockpit
      token-upload: true                # Use direct API for token auth
      auto-create-testcases: true       # Auto-create missing test cases
      template: Empty
      planned-in: RHEL-10.0.0
      assignee: jscotka
      pool-team: rhel-cockpit
      arch: x86_64
      upload: false  # Set to true when you have valid credentials
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
  - **Title**: `[polarion ID] - [distro] - [plan name]`
    - Example: `20251113-1425 - RHEL-9.8 - /Sanity/upstream-direct/plans/browser`
  - **Metadata**: planned-in, assignee, pool-team, arch (normalized)
  - **Description** (HTML-formatted):
    - Plan summary
    - Plan description
    - Environment variables
    - Provision details (method, image, memory, disk, addresses, distro, kernel, etc.)
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

## See Also

- Main integration guide: `examples/polarion-reportportal-README.md`
- Polarion reporter docs: `tmt run report --how polarion --help`
- ReportPortal reporter docs: `tmt run report --how reportportal --help`

