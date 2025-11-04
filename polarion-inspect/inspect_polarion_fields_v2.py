#!/usr/bin/env python3
"""
Inspect Polarion work item fields by directly examining the Python object
"""

def inspect_fields():
    from pylero.work_item import _WorkItem
    
    project_id = 'RHELCockpit'
    work_item_id = 'RHELCOCKPIT-710'
    
    print(f"Fetching work item: {work_item_id}\n")
    
    try:
        wi = _WorkItem(project_id=project_id, work_item_id=work_item_id)
        print(f"✓ Work item: {wi.work_item_id} - {wi.title}\n")
        
        print("=" * 80)
        print("ALL READABLE ATTRIBUTES AND THEIR TYPES")
        print("=" * 80)
        
        # Get all attributes
        all_attrs = {}
        for attr in dir(wi):
            if not attr.startswith('_') and not callable(getattr(wi, attr, None)):
                try:
                    value = getattr(wi, attr)
                    value_type = type(value).__name__
                    value_str = str(value)[:60] if value is not None else 'None'
                    all_attrs[attr] = (value_type, value_str, value)
                except Exception as e:
                    all_attrs[attr] = ('error', str(e)[:60], None)
        
        # Categorize fields
        standard_fields = {
            'work_item_id', 'title', 'description', 'type', 'status', 
            'priority', 'severity', 'author', 'created', 'updated',
            'assignee', 'planned_in', 'planned_start', 'planned_end',
            'due_date', 'resolved_on', 'resolution', 'initial_estimate',
            'remaining_estimate', 'time_spent', 'categories', 'comments',
            'attachments', 'hyperlinks', 'linked_work_items',
            'linked_work_items_derived', 'externally_linked_work_items',
            'approvals', 'planning_constraints', 'work_records',
            'auto_suspect', 'linked_revisions', 'linked_revisions_derived'
        }
        
        print("\n📋 STANDARD FIELDS:")
        print("-" * 80)
        print(f"{'Field Name':<30} | {'Type':<20} | {'Current Value':<30}")
        print("-" * 80)
        
        for field in sorted(all_attrs.keys()):
            if field in standard_fields:
                vtype, vstr, _ = all_attrs[field]
                print(f"{field:<30} | {vtype:<20} | {vstr:<30}")
        
        print("\n🔧 CUSTOM/OTHER FIELDS:")
        print("-" * 80)
        print(f"{'Field Name':<30} | {'Type':<20} | {'Current Value':<30}")
        print("-" * 80)
        
        custom_fields = []
        for field in sorted(all_attrs.keys()):
            if field not in standard_fields:
                vtype, vstr, _ = all_attrs[field]
                custom_fields.append(field)
                print(f"{field:<30} | {vtype:<20} | {vstr:<30}")
        
        # Now check for enum fields
        print("\n" + "=" * 80)
        print("ENUM FIELDS ANALYSIS")
        print("=" * 80)
        
        from pylero.enum_option_id import EnumOptionId
        
        enum_fields = {}
        for field_name, (vtype, vstr, value) in all_attrs.items():
            if value is not None:
                # Check if it's an EnumOptionId
                if isinstance(value, EnumOptionId):
                    enum_fields[field_name] = ('single_enum', value)
                # Check if it's a list of EnumOptionIds
                elif isinstance(value, list) and value and isinstance(value[0], EnumOptionId):
                    enum_fields[field_name] = ('list_enum', value)
        
        if enum_fields:
            print("\n✓ Found enum fields:\n")
            for field_name, (enum_type, value) in enum_fields.items():
                print(f"  {field_name} ({enum_type}):")
                if enum_type == 'single_enum':
                    print(f"    Current: {value.id}")
                else:  # list_enum
                    print(f"    Current: {[v.id for v in value]}")
        else:
            print("\n⚠ No enum fields found with values")
        
        # Try to get available enum values from the service
        print("\n" + "=" * 80)
        print("AVAILABLE ENUM VALUES (attempting to query Polarion)")
        print("=" * 80)
        
        # List of fields that are typically enums in Polarion
        potential_enum_fields = [
            'status', 'priority', 'severity', 'resolution',
            'planned_in', 'planned_start', 'planned_end',
            'subsystemteam', 'casecomponent', 'component',
            'team', 'type'
        ]
        
        print("\nAttempting to query enum values from Polarion service...")
        
        try:
            session = wi.session
            service = session.tracker_client.service
            
            for field_name in potential_enum_fields:
                try:
                    # Try to get enum options
                    enum_id = field_name
                    result = service.getEnumOptionIdsForId(enum_id)
                    
                    if result:
                        print(f"\n📌 {field_name}: ({len(result)} values)")
                        # Show first 15 values
                        for idx, opt in enumerate(result[:15], 1):
                            print(f"    {idx:2d}. {opt.id}")
                        if len(result) > 15:
                            print(f"    ... and {len(result) - 15} more")
                
                except Exception as e:
                    error_msg = str(e)
                    if 'No enum found' not in error_msg and 'not found' not in error_msg.lower():
                        print(f"\n  {field_name}: ⚠ {error_msg[:60]}")
        
        except Exception as e:
            print(f"\n⚠ Could not query enum values: {e}")
        
        # Try to inspect what custom fields are defined in the project
        print("\n" + "=" * 80)
        print("CUSTOM FIELD KEYS")
        print("=" * 80)
        
        try:
            # Check _suds_object for custom field info
            if hasattr(wi, '_suds_object'):
                suds = wi._suds_object
                print(f"\nSUDS object type: {type(suds)}")
                
                # Try to see what's in the SUDS object
                if hasattr(suds, '__dict__'):
                    print("\nSUDS __dict__ keys:")
                    for key in sorted(suds.__dict__.keys()):
                        val = suds.__dict__[key]
                        print(f"  {key}: {type(val).__name__}")
                
                if hasattr(suds, '__keylist__'):
                    print(f"\nSUDS __keylist__: {suds.__keylist__}")
        
        except Exception as e:
            print(f"\n⚠ Error inspecting SUDS object: {e}")
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"\n✓ Total fields found: {len(all_attrs)}")
        print(f"  - Standard fields: {len([f for f in all_attrs if f in standard_fields])}")
        print(f"  - Custom fields: {len(custom_fields)}")
        print(f"  - Enum fields with values: {len(enum_fields)}")
        
        if custom_fields:
            print(f"\n🔧 Custom fields detected: {', '.join(custom_fields[:10])}")
            if len(custom_fields) > 10:
                print(f"   ... and {len(custom_fields) - 10} more")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    inspect_fields()

