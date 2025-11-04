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
    
    # Get defined custom field keys
    try:
        custom_keys = service.getDefinedCustomFieldKeys(project, 'WorkItem')
        
        if custom_keys:
            click.echo(f"\n✓ Found {len(custom_keys)} custom field keys:\n")
            
            for key in sorted(custom_keys):
                try:
                    field_type = service.getDefinedCustomFieldType(
                        project, 'WorkItem', key
                    )
                    click.echo(f"  {key:<30} | {field_type}")
                except:
                    click.echo(f"  {key:<30} | (type unknown)")
        else:
            click.echo("\n⚠ No custom fields found")
    
    except Exception as e:
        click.echo(f"✗ Error: {e}")
    
    # Try to get current values
    click.echo("\n" + "=" * 80)
    click.echo("CURRENT VALUES")
    click.echo("=" * 80 + "\n")
    
    if custom_keys:
        for key in sorted(custom_keys[:20]):
            try:
                value = service.getCustomField(wi.uri, key)
                value_str = str(value)[:50] if value else 'None'
                click.echo(f"  {key:<30} = {value_str}")
            except:
                pass


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
@click.option('--field', help='Specific field to query')
def enums(project, work_item, field):
    """Show enum values for fields"""
    from pylero.work_item import _WorkItem
    
    wi = _WorkItem(project_id=project, work_item_id=work_item)
    session = wi.session
    service = session.tracker_client.service
    
    click.echo("=" * 80)
    click.echo("ENUM VALUES")
    click.echo("=" * 80)
    
    # Predefined list of common enum fields
    enum_fields = [
        'status', 'priority', 'severity', 'resolution', 'type',
        'planned_in', 'subsystemteam', 'casecomponent'
    ]
    
    if field:
        enum_fields = [field]
    
    for enum_id in enum_fields:
        try:
            result = service.getAllEnumOptionIdsForId(enum_id)
            
            if result:
                click.echo(f"\n📌 {enum_id.upper()}: ({len(result)} values)")
                click.echo("-" * 60)
                
                for idx, val in enumerate(result[:20], 1):
                    val_id = val.id if hasattr(val, 'id') else str(val)
                    val_name = val.name if hasattr(val, 'name') else ''
                    
                    if val_name and val_name != val_id:
                        click.echo(f"  {idx:3d}. {val_id:<40} # {val_name}")
                    else:
                        click.echo(f"  {idx:3d}. {val_id}")
                
                if len(result) > 20:
                    click.echo(f"  ... and {len(result) - 20} more")
        
        except Exception as e:
            if 'not found' not in str(e).lower():
                click.echo(f"\n✗ {enum_id}: {e}")


if __name__ == '__main__':
    cli()
