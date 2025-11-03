#!/usr/bin/env python3
"""
Polarion Inspector - Tool for inspecting Polarion work items and discovering custom fields

Usage:
    polarion-inspect.py fields --project PROJECT --work-item ID     # Inspect work item fields
    polarion-inspect.py custom --project PROJECT                    # Discover custom fields
    polarion-inspect.py methods                                     # List service methods
    polarion-inspect.py enums --project PROJECT [--field FIELD]    # Show enum values
"""

import click


@click.group()
def cli():
    """Polarion Inspector - Inspect work items and discover custom fields"""
    pass


@cli.command()
@click.option('--project', required=True, help='Polarion project ID')
@click.option('--work-item', required=True, help='Work item ID')
def fields(project, work_item):
    """Inspect all fields in a work item"""
    from pylero.work_item import _WorkItem
    
    click.echo(f"Fetching work item: {work_item}\n")
    
    wi = _WorkItem(project_id=project, work_item_id=work_item)
    click.echo(f"✓ Work item: {wi.work_item_id} - {wi.title}\n")
    
    click.echo("=" * 80)
    click.echo("WORK ITEM FIELDS")
    click.echo("=" * 80)
    
    # Get all readable attributes
    all_attrs = {}
    for attr in dir(wi):
        if not attr.startswith('_') and not callable(getattr(wi, attr, None)):
            try:
                value = getattr(wi, attr)
                value_type = type(value).__name__
                value_str = str(value)[:50] if value is not None else 'None'
                all_attrs[attr] = (value_type, value_str)
            except:
                pass
    
    click.echo(f"\n{'Field':<30} | {'Type':<20} | {'Value':<30}")
    click.echo("-" * 85)
    
    for field in sorted(all_attrs.keys()):
        vtype, vstr = all_attrs[field]
        click.echo(f"{field:<30} | {vtype:<20} | {vstr:<30}")
    
    click.echo(f"\n✓ Total fields: {len(all_attrs)}")


@cli.command()
@click.option('--project', required=True, help='Polarion project ID')
@click.option('--work-item', default='RHELCOCKPIT-723', 
              help='Sample work item ID (default: RHELCOCKPIT-723)')
def custom(project, work_item):
    """Discover custom fields for a project"""
    from pylero.work_item import _WorkItem
    
    click.echo(f"Connecting to project: {project}\n")
    
    wi = _WorkItem(project_id=project, work_item_id=work_item)
    session = wi.session
    service = session.tracker_client.service
    
    click.echo("=" * 80)
    click.echo("CUSTOM FIELDS DISCOVERY")
    click.echo("=" * 80)
    
    # Get custom field keys from actual work item
    try:
        custom_keys = service.getCustomFieldKeys(wi.uri)
        
        if custom_keys:
            click.echo(f"\n✓ Found {len(custom_keys)} custom field keys:\n")
            
            # Get values and types
            for key in sorted(custom_keys):
                try:
                    # Get the field type
                    field_type = str(service.getCustomFieldType(wi.uri, key))
                    
                    # Get current value
                    value = service.getCustomField(wi.uri, key)
                    
                    # Format value
                    if value is None:
                        value_str = '(not set)'
                    elif hasattr(value, 'value'):
                        # CustomField object
                        val = value.value
                        if hasattr(val, 'id'):
                            value_str = str(val.id) + " (enum)"
                        else:
                            value_str = str(val)[:40] if val else '(not set)'
                    else:
                        value_str = str(value)[:40]
                    
                    click.echo(f"  {key:<25} | {field_type:<15} | {value_str}")
                except Exception as e:
                    error_msg = str(e).replace('{', '{{').replace('}', '}}')
                    click.echo(f"  {key:<25} | (error: {error_msg[:30]})")
        else:
            click.echo("\n⚠ No custom fields found")
    
    except Exception as e:
        click.echo(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


@cli.command()
@click.option('--all', is_flag=True, help='Show all methods')
@click.option('--project', default='RHELCockpit', help='Polarion project ID (default: RHELCockpit)')
@click.option('--work-item', default='RHELCOCKPIT-723',
              help='Sample work item ID (default: RHELCOCKPIT-723)')
def methods(all, project, work_item):
    """List all available Polarion service methods"""
    from pylero.work_item import _WorkItem
    
    click.echo("Connecting to Polarion...\n")
    
    # Use a sample work item to get session
    wi = _WorkItem(project_id=project, work_item_id=work_item)
    session = wi.session
    client = session.tracker_client
    
    click.echo("=" * 80)
    click.echo("POLARION SERVICE METHODS")
    click.echo("=" * 80 + "\n")
    
    # Get methods from WSDL
    port = client.wsdl.services[0].ports[0]
    method_list = [method.name for method in port.methods.values()]
    
    click.echo(f"Found {len(method_list)} methods\n")
    
    # Categorize
    categories = {
        'Enum': [m for m in method_list if 'enum' in m.lower()],
        'Field/Custom': [m for m in method_list if 'field' in m.lower() or 'custom' in m.lower()],
        'Work Item': [m for m in method_list if 'workitem' in m.lower()],
    }
    
    for cat_name, cat_methods in categories.items():
        if cat_methods:
            click.echo(f"\n📌 {cat_name.upper()}-RELATED ({len(cat_methods)}):")
            for m in sorted(cat_methods)[:15]:
                click.echo(f"  - {m}")
            if len(cat_methods) > 15:
                click.echo(f"  ... and {len(cat_methods) - 15} more")
    
    if all:
        click.echo(f"\n\n💡 ALL {len(method_list)} METHODS:")
        click.echo("-" * 80)
        for idx, m in enumerate(sorted(method_list), 1):
            click.echo(f"{idx:3d}. {m}")


@cli.command()
@click.option('--project', required=True, help='Polarion project ID')
@click.option('--work-item', default='RHELCOCKPIT-723',
              help='Sample work item ID (default: RHELCOCKPIT-723)')
@click.option('--field', help='Specific field to query (e.g., status, priority)')
def enums(project, work_item, field):
    """Show enum fields and their current values from work item"""
    from pylero.work_item import _WorkItem
    from pylero.enum_option_id import EnumOptionId
    
    wi = _WorkItem(project_id=project, work_item_id=work_item)
    
    click.echo("=" * 80)
    click.echo("ENUM FIELDS IN WORK ITEM")
    click.echo("=" * 80)
    
    # Discover enum fields from the work item
    enum_fields = {}
    
    for attr in dir(wi):
        if attr.startswith('_') or callable(getattr(wi, attr, None)):
            continue
        
        try:
            value = getattr(wi, attr)
            
            # Check if it's an EnumOptionId or list of EnumOptionIds
            if isinstance(value, EnumOptionId):
                enum_fields[attr] = ('single', value)
            elif isinstance(value, list) and value and isinstance(value[0], EnumOptionId):
                enum_fields[attr] = ('list', value)
        except:
            pass
    
    # Filter by specific field if requested
    if field:
        if field in enum_fields:
            enum_fields = {field: enum_fields[field]}
        else:
            click.echo(f"\n✗ Field '{field}' not found or not an enum field")
            click.echo(f"\nAvailable enum fields: {', '.join(sorted(enum_fields.keys()))}")
            return
    
    if not enum_fields:
        click.echo("\n⚠ No enum fields found in work item")
        return
    
    click.echo(f"\n✓ Found {len(enum_fields)} enum field(s):\n")
    
    for field_name, (enum_type, value) in sorted(enum_fields.items()):
        if enum_type == 'single':
            click.echo(f"📌 {field_name.upper()}")
            click.echo(f"  Type: Single enum")
            click.echo(f"  Current value: {value.id}")
            if hasattr(value, 'name') and value.name:
                click.echo(f"  Display name: {value.name}")
        else:  # list
            click.echo(f"\n📌 {field_name.upper()}")
            click.echo(f"  Type: List enum ({len(value)} values)")
            click.echo(f"  Current values:")
            for idx, val in enumerate(value, 1):
                val_id = val.id if hasattr(val, 'id') else str(val)
                val_name = val.name if hasattr(val, 'name') and val.name else ''
                if val_name:
                    click.echo(f"    {idx}. {val_id} ({val_name})")
                else:
                    click.echo(f"    {idx}. {val_id}")
        click.echo()


if __name__ == '__main__':
    cli()
