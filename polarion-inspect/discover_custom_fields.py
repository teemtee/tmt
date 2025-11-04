#!/usr/bin/env python3
"""
Discover custom fields for requirement work items using Polarion service methods
"""

def discover_custom_fields():
    from pylero.work_item import _WorkItem
    
    project_id = 'RHELCockpit'
    work_item_id = 'RHELCOCKPIT-710'
    
    print("=" * 80)
    print("DISCOVERING CUSTOM FIELDS FOR REQUIREMENT WORK ITEMS")
    print("=" * 80)
    
    try:
        wi = _WorkItem(project_id=project_id, work_item_id=work_item_id)
        print(f"\n✓ Connected to work item: {wi.work_item_id}")
        print(f"  Type: {wi.type}\n")
        
        session = wi.session
        service = session.tracker_client.service
        
        # Get defined custom field keys for this project and work item type
        print("=" * 80)
        print("METHOD 1: getDefinedCustomFieldKeys")
        print("=" * 80)
        
        try:
            custom_field_keys = service.getDefinedCustomFieldKeys(
                project_id, 
                'WorkItem'  # The work item object type
            )
            
            if custom_field_keys:
                print(f"\n✓ Found {len(custom_field_keys)} custom field keys:\n")
                for idx, key in enumerate(sorted(custom_field_keys), 1):
                    print(f"  {idx:3d}. {key}")
            else:
                print("\n⚠ No custom field keys found")
        except Exception as e:
            print(f"\n✗ Error: {e}")
        
        # Try to get custom field types
        print("\n" + "=" * 80)
        print("METHOD 2: getDefinedCustomFieldType (for each key)")
        print("=" * 80)
        
        if custom_field_keys:
            print("\nQuerying type for each custom field:\n")
            
            custom_fields_info = []
            for key in sorted(custom_field_keys):
                try:
                    field_type = service.getDefinedCustomFieldType(
                        project_id,
                        'WorkItem',
                        key
                    )
                    
                    custom_fields_info.append((key, field_type))
                    print(f"  {key:<30} | {field_type}")
                
                except Exception as e:
                    print(f"  {key:<30} | Error: {str(e)[:40]}")
        
        # Try to get available enum values for fields that might be enums
        print("\n" + "=" * 80)
        print("METHOD 3: getAllEnumOptionIdsForId (for enum fields)")
        print("=" * 80)
        
        # Try known field IDs that might be enums
        potential_enums = [
            'status', 'severity', 'priority', 'type', 'resolution',
            'subsystemteam', 'casecomponent', 'planned_in',
        ]
        
        # Add any custom fields that look like enums
        if custom_field_keys:
            potential_enums.extend([k for k in custom_field_keys if k not in potential_enums])
        
        print(f"\nChecking {len(potential_enums)} potential enum fields...\n")
        
        enum_fields = {}
        for enum_id in sorted(potential_enums):
            try:
                # Try to get enum options
                result = service.getAllEnumOptionIdsForId(enum_id)
                
                if result:
                    enum_fields[enum_id] = result
                    print(f"✓ {enum_id}: {len(result)} values")
            
            except Exception as e:
                error_str = str(e)
                if 'No enum found' not in error_str and 'not found' not in error_str.lower():
                    pass  # Skip "not found" errors silently
        
        # Display enum values
        if enum_fields:
            print("\n" + "=" * 80)
            print("ENUM FIELDS WITH VALUES")
            print("=" * 80)
            
            for enum_id, values in sorted(enum_fields.items()):
                print(f"\n📌 {enum_id.upper()}: ({len(values)} values)")
                print("-" * 60)
                
                for idx, val in enumerate(values[:25], 1):
                    val_id = val.id if hasattr(val, 'id') else str(val)
                    val_name = val.name if hasattr(val, 'name') else ''
                    
                    if val_name and val_name != val_id:
                        print(f"  {idx:3d}. {val_id:<40} # {val_name}")
                    else:
                        print(f"  {idx:3d}. {val_id}")
                
                if len(values) > 25:
                    print(f"  ... and {len(values) - 25} more")
        
        # Try to get current values from the work item
        print("\n" + "=" * 80)
        print("METHOD 4: getCustomField (get current values)")
        print("=" * 80)
        
        if custom_field_keys:
            print("\nReading current values from work item:\n")
            
            for key in sorted(custom_field_keys[:20]):  # First 20
                try:
                    value = service.getCustomField(wi.uri, key)
                    value_str = str(value)[:60] if value is not None else 'None'
                    print(f"  {key:<30} = {value_str}")
                except Exception as e:
                    pass  # Skip errors
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        if custom_field_keys:
            print(f"\n✓ Total custom fields: {len(custom_field_keys)}")
        if enum_fields:
            print(f"✓ Enum fields found: {len(enum_fields)}")
            print(f"  - {', '.join(sorted(enum_fields.keys()))}")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    discover_custom_fields()

