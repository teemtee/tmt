#!/usr/bin/env python3
"""
Polarion Inspector - Tool for inspecting Polarion work items and discovering custom fields

Usage:
    polarion-inspect.py fields --project PROJECT --work-item ID     # Inspect work item fields
    polarion-inspect.py custom --project PROJECT                    # Discover custom fields
    polarion-inspect.py methods                                     # List service methods
    polarion-inspect.py enums --project PROJECT [--field FIELD]    # Show enum values
"""

import argparse
import sys


def cmd_fields(args):
    """Inspect all fields in a work item"""
    from pylero.work_item import _WorkItem
    
    print(f"Fetching work item: {args.work_item}\n")
    
    wi = _WorkItem(project_id=args.project, work_item_id=args.work_item)
    print(f"✓ Work item: {wi.work_item_id} - {wi.title}\n")
    
    print("=" * 80)
    print("WORK ITEM FIELDS")
    print("=" * 80)
    
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
    
    print(f"\n{'Field':<30} | {'Type':<20} | {'Value':<30}")
    print("-" * 85)
    
    for field in sorted(all_attrs.keys()):
        vtype, vstr = all_attrs[field]
        print(f"{field:<30} | {vtype:<20} | {vstr:<30}")
    
    print(f"\n✓ Total fields: {len(all_attrs)}")


def cmd_custom(args):
    """Discover custom fields for a project"""
    from pylero.work_item import _WorkItem
    
    # Use a sample work item to connect
    print(f"Connecting to project: {args.project}\n")
    
    wi = _WorkItem(project_id=args.project, work_item_id=args.work_item)
    session = wi.session
    service = session.tracker_client.service
    
    print("=" * 80)
    print("CUSTOM FIELDS DISCOVERY")
    print("=" * 80)
    
    # Get defined custom field keys
    try:
        custom_keys = service.getDefinedCustomFieldKeys(args.project, 'WorkItem')
        
        if custom_keys:
            print(f"\n✓ Found {len(custom_keys)} custom field keys:\n")
            
            for key in sorted(custom_keys):
                try:
                    field_type = service.getDefinedCustomFieldType(
                        args.project, 'WorkItem', key
                    )
                    print(f"  {key:<30} | {field_type}")
                except:
                    print(f"  {key:<30} | (type unknown)")
        else:
            print("\n⚠ No custom fields found")
    
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Try to get current values
    print("\n" + "=" * 80)
    print("CURRENT VALUES")
    print("=" * 80 + "\n")
    
    if custom_keys:
        for key in sorted(custom_keys[:20]):
            try:
                value = service.getCustomField(wi.uri, key)
                value_str = str(value)[:50] if value else 'None'
                print(f"  {key:<30} = {value_str}")
            except:
                pass


def cmd_methods(args):
    """List all available Polarion service methods"""
    from pylero.work_item import _WorkItem
    
    print("Connecting to Polarion...\n")
    
    # Use a sample work item to get session
    wi = _WorkItem(project_id='RHELCockpit', work_item_id='RHELCOCKPIT-710')
    session = wi.session
    client = session.tracker_client
    
    print("=" * 80)
    print("POLARION SERVICE METHODS")
    print("=" * 80 + "\n")
    
    # Get methods from WSDL
    port = client.wsdl.services[0].ports[0]
    methods = [method.name for method in port.methods.values()]
    
    print(f"Found {len(methods)} methods\n")
    
    # Categorize
    categories = {
        'Enum': [m for m in methods if 'enum' in m.lower()],
        'Field/Custom': [m for m in methods if 'field' in m.lower() or 'custom' in m.lower()],
        'Work Item': [m for m in methods if 'workitem' in m.lower()],
    }
    
    for cat_name, cat_methods in categories.items():
        if cat_methods:
            print(f"\n📌 {cat_name.upper()}-RELATED ({len(cat_methods)}):")
            for m in sorted(cat_methods)[:15]:
                print(f"  - {m}")
            if len(cat_methods) > 15:
                print(f"  ... and {len(cat_methods) - 15} more")
    
    if args.all:
        print(f"\n\n💡 ALL {len(methods)} METHODS:")
        print("-" * 80)
        for idx, m in enumerate(sorted(methods), 1):
            print(f"{idx:3d}. {m}")


def cmd_enums(args):
    """Show enum values for fields"""
    from pylero.work_item import _WorkItem
    
    wi = _WorkItem(project_id=args.project, work_item_id=args.work_item)
    session = wi.session
    service = session.tracker_client.service
    
    print("=" * 80)
    print("ENUM VALUES")
    print("=" * 80)
    
    # Predefined list of common enum fields
    enum_fields = [
        'status', 'priority', 'severity', 'resolution', 'type',
        'planned_in', 'subsystemteam', 'casecomponent'
    ]
    
    if args.field:
        enum_fields = [args.field]
    
    for enum_id in enum_fields:
        try:
            result = service.getAllEnumOptionIdsForId(enum_id)
            
            if result:
                print(f"\n📌 {enum_id.upper()}: ({len(result)} values)")
                print("-" * 60)
                
                for idx, val in enumerate(result[:20], 1):
                    val_id = val.id if hasattr(val, 'id') else str(val)
                    val_name = val.name if hasattr(val, 'name') else ''
                    
                    if val_name and val_name != val_id:
                        print(f"  {idx:3d}. {val_id:<40} # {val_name}")
                    else:
                        print(f"  {idx:3d}. {val_id}")
                
                if len(result) > 20:
                    print(f"  ... and {len(result) - 20} more")
        
        except Exception as e:
            if 'not found' not in str(e).lower():
                print(f"\n✗ {enum_id}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Polarion Inspector - Inspect work items and discover custom fields',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Inspect work item fields
  %(prog)s fields --project RHELCockpit --work-item RHELCOCKPIT-710
  
  # Discover custom fields
  %(prog)s custom --project RHELCockpit
  
  # List service methods
  %(prog)s methods
  
  # Show enum values
  %(prog)s enums --project RHELCockpit
  %(prog)s enums --project RHELCockpit --field status
'''
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True
    
    # fields command
    fields_parser = subparsers.add_parser('fields', help='Inspect work item fields')
    fields_parser.add_argument('--project', required=True, help='Polarion project ID')
    fields_parser.add_argument('--work-item', required=True, help='Work item ID')
    
    # custom command
    custom_parser = subparsers.add_parser('custom', help='Discover custom fields')
    custom_parser.add_argument('--project', required=True, help='Polarion project ID')
    custom_parser.add_argument('--work-item', default='RHELCOCKPIT-710', 
                               help='Sample work item ID (default: RHELCOCKPIT-710)')
    
    # methods command
    methods_parser = subparsers.add_parser('methods', help='List service methods')
    methods_parser.add_argument('--all', action='store_true', help='Show all methods')
    
    # enums command
    enums_parser = subparsers.add_parser('enums', help='Show enum values')
    enums_parser.add_argument('--project', required=True, help='Polarion project ID')
    enums_parser.add_argument('--work-item', default='RHELCOCKPIT-710',
                              help='Sample work item ID (default: RHELCOCKPIT-710)')
    enums_parser.add_argument('--field', help='Specific field to query')
    
    args = parser.parse_args()
    
    try:
        if args.command == 'fields':
            cmd_fields(args)
        elif args.command == 'custom':
            cmd_custom(args)
        elif args.command == 'methods':
            cmd_methods(args)
        elif args.command == 'enums':
            cmd_enums(args)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
