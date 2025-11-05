# Polarion Report Integration Example

This example demonstrates how to use the Polarion report plugin to automatically upload test run results to Polarion with token authentication.

## Overview

This example contains:
- A simple test (`test.sh`) that performs basic assertions
- Test metadata (`test.fmf`) with description and tags
- A test plan (`plan.fmf`) configured with Polarion reporter

## Prerequisites

1. **Polarion Access**: You need access to a Polarion instance
2. **Pylero Configuration**: Configure `~/.pylero` with token authentication
3. **Exported Test Case**: The test must be exported to Polarion first

## Setup

### 1. Configure Polarion Authentication

**IMPORTANT**: Polarion's XUnit importer endpoint does NOT support token authentication. You have two options:

#### Option A: Password Authentication (For Automatic Upload)

Create or update `~/.pylero` with password authentication:

```ini
[webservice]
url=https://polarion.engineering.redhat.com/polarion
svn_repo=https://polarion.engineering.redhat.com/repo
default_project=RHELCockpit
user=your_username
password=your_password
```

**Use this if**: You want `tmt` to automatically upload results to Polarion.

#### Option B: Token Authentication (For Report Generation Only)

Create or update `~/.pylero` with token authentication:

```ini
[webservice]
url=https://polarion.engineering.redhat.com/polarion
svn_repo=https://polarion.engineering.redhat.com/repo
default_project=RHELCockpit
token=your_personal_access_token_here
```

**Use this if**: You want to use tokens for test export and generate XUnit files, but upload manually.

**To get a Polarion token:**
1. Log in to Polarion web interface
2. Go to your user preferences/settings
3. Generate a personal access token
4. Copy it to your `~/.pylero` config

### 2. Export Test Case to Polarion

Before running the test, you need to export the test case metadata to Polarion:

```bash
cd examples/polarion-run-report

# Export the specific test to Polarion (creates a test case work item)
tmt tests export --how polarion --project-id RHELCockpit --create /examples/polarion-run-report/test
```

This will:
- Create a new test case in Polarion's RHELCockpit project
- Add a UUID to the test metadata
- Store the Polarion work item ID for future reference

**Note**: The `--create` flag is only needed the first time. After that, tmt will update the existing test case.

## Running the Test

### Option 1: Generate Report (Works with Token or Password)

Run the test and generate XUnit file (no upload):

```bash
# Run from the example directory
cd examples/polarion-run-report
tmt run --all provision --how local --feeling-safe

# Or run from the tmt root directory
tmt run --all provision --how local --feeling-safe plan --name /examples/polarion-run-report
```

**Note**: The `--feeling-safe` flag is required when using the `local` provisioner.

This will:
1. Discover the test
2. Provision a local environment
3. Execute the test
4. Generate an XUnit file with Polarion metadata
5. Save the XUnit file (no upload, works with token auth)

### Option 2: Run with Automatic Upload (Requires Password)

To automatically upload results to Polarion, you need password authentication:

```bash
# 1. Configure password in ~/.pylero (see setup section)
# 2. Enable upload in plan.fmf: upload: true
# 3. Run the test
tmt run --all provision --how local --feeling-safe plan --name /examples/polarion-run-report
```

This uploads results automatically using password authentication.

### Option 3: Manual Upload (Requires Password)

Generate the report first, then upload manually:

```bash
# 1. Run test with upload disabled (works with token auth)
cd examples/polarion-run-report
tmt run --all provision --how local --feeling-safe

# 2. Find the generated XUnit file
# It's usually at: /var/tmp/tmt/run-XXX/.../report/default-0/xunit.xml

# 3. Upload manually with password (token NOT supported by XUnit importer)
curl -k -u USERNAME:PASSWORD \
  -X POST -F file=@xunit.xml \
  https://polarion.engineering.redhat.com/polarion/import/xunit
```

**Note**: Manual upload also requires password authentication. The XUnit importer endpoint does not accept tokens.

## Customizing the Plan

You can customize the Polarion report settings in `plan.fmf`:

```yaml
report:
    how: polarion
    project-id: RHELCockpit
    title: my_custom_test_run
    template: Empty  # Test run template (default: 'Empty')
    description: My custom test run description
    planned-in: RHEL-9.5.0
    pool-team: sst_tmt
    arch: x86_64
    assignee: myusername
    upload: true  # Works with both token and password auth!
```

## Example Output

When the test runs successfully, you'll see output like this:

```
/var/tmp/tmt/run-767

/examples/polarion-run-report/plan
    discover
        summary: 1 test selected
    provision
        summary: 1 guest provisioned
    prepare
        summary: 1 preparation applied
    execute
        summary: 1 test executed
    report
        how: polarion
        xUnit file saved at: /var/tmp/tmt/run-767/.../xunit.xml
        summary: 1 test passed

total: 1 test passed
```

The generated XUnit file will contain Polarion metadata:

```xml
<testcase name="/examples/polarion-run-report/test">
  <properties>
    <property name="polarion-testcase-id" value="RHELCOCKPIT-837"/>
    <property name="polarion-testcase-project-id" value="RHELCockpit"/>
  </properties>
</testcase>
```

## Verifying Results

After running the test with upload enabled:

1. **Check the terminal output**: Look for "Response code is 200" (if upload is enabled)
2. **Log in to Polarion**: Navigate to your project
3. **Go to Test Runs**: Find your test run by title
4. **View Results**: Check that the test result was uploaded correctly

The test run title format is: `planname_YYYYMMDDHHMMSS`

## Troubleshooting

### Error: "Polarion authentication not configured"
- Check that `~/.pylero` exists and has either `token` or `password` configured
- Verify the token is valid and not expired

### Error: "Test Case 'X' is not exported to Polarion"
- Run `tmt tests export --how polarion --project-id RHELCockpit --create` first
- Check that the test has a UUID in its metadata

### Error: "Response code is 401" or "Response code is 403"
- Token is invalid or expired - generate a new one
- Check that your Polarion user has permission to upload test runs

### The XUnit file is generated but not uploaded
- Check if `upload: false` is set in the plan
- Verify your network connectivity to Polarion
- Check the logs for detailed error messages

## Environment Variables

You can also use environment variables instead of plan configuration:

```bash
# Set Polarion project
export TMT_PLUGIN_REPORT_POLARION_PROJECT_ID=RHELCockpit

# Set test run title
export TMT_PLUGIN_REPORT_POLARION_TITLE=my_test_run

# Disable upload
export TMT_PLUGIN_REPORT_POLARION_UPLOAD=0

# Run the test
tmt run -vv
```

## Example Output

```
/examples/polarion-run-report/plan
    discover
        how: fmf
        summary: 1 test selected
    provision
        how: local
    execute
        how: tmt
        summary: 1 test passed
    report
        how: polarion
        summary: Response code is 200 with text: Import successful
        summary: xUnit file saved at /var/tmp/tmt/run-001/plan/report/default-0/xunit.xml
```

## Additional Resources

- [TMT Documentation](https://tmt.readthedocs.io/)
- [Pylero Documentation](https://github.com/RedHatQE/pylero)
- [Polarion XUnit Importer](https://mojo.redhat.com/docs/DOC-1075945)
- [Token Authentication Guide](../../POLARION_TOKEN_AUTH.md)

