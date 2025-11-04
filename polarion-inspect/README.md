# Polarion Inspector

Tool for inspecting Polarion work items and discovering custom fields.

## Prerequisites

```bash
pip install pylero
```

Configure `~/.pylero`:
```ini
[webservice]
url=https://polarion.engineering.redhat.com/polarion
default_project=RHELCockpit
token=your_token_here
```

## Usage

Make the script executable:
```bash
chmod +x polarion-inspect.py
```

### Commands

**Inspect work item fields:**
```bash
./polarion-inspect.py fields --project RHELCockpit --work-item RHELCOCKPIT-710
```

**Discover custom fields:**
```bash
./polarion-inspect.py custom --project RHELCockpit
```

**List Polarion service methods:**
```bash
./polarion-inspect.py methods
./polarion-inspect.py methods --all  # Show all methods
```

**Show enum values:**
```bash
./polarion-inspect.py enums --project RHELCockpit
./polarion-inspect.py enums --project RHELCockpit --field status
```

## Examples

```bash
# Quick field inspection
./polarion-inspect.py fields --project RHELCockpit --work-item RHELCOCKPIT-710

# Find what custom fields are available
./polarion-inspect.py custom --project RHELCockpit

# Check enum options for a specific field
./polarion-inspect.py enums --project RHELCockpit --field priority
```

## Output

The tool provides formatted tables showing:
- Field names, types, and current values
- Custom field definitions and types
- Available enum values for enum fields
- Polarion SOAP service methods

## Troubleshooting

If you get authentication errors:
1. Check `~/.pylero` configuration
2. Verify your token is valid
3. Ensure you have access to the project

If custom fields aren't showing:
- They may not be enabled for the work item type
- Check Polarion admin settings under Administration → Custom Fields

