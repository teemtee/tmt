#!/usr/bin/env python3
"""
Deep inspection of the SUDS work item object to find custom fields
"""

def inspect_suds_object():
    from pylero.work_item import _WorkItem
    
    project_id = 'RHELCockpit'
    work_item_id = 'RHELCOCKPIT-710'
    
    print("=" * 80)
    print("DEEP SUDS OBJECT INSPECTION")
    print("=" * 80)
    
    try:
        wi = _WorkItem(project_id=project_id, work_item_id=work_item_id)
        print(f"\n✓ Work item: {wi.work_item_id}\n")
        
        # Get the SUDS object
        suds = wi._suds_object
        print(f"SUDS object type: {type(suds)}\n")
        
        # Get the keylist (all fields)
        if hasattr(suds, '__keylist__'):
            keylist = suds.__keylist__
            print(f"Total fields in __keylist__: {len(keylist)}\n")
            
            # Try to read each field
            print("=" * 80)
            print("ALL FIELDS IN SUDS OBJECT")
            print("=" * 80)
            print(f"\n{'Field Name':<35} | {'Type':<20} | {'Value':<40}")
            print("-" * 110)
            
            for key in sorted(keylist):
                try:
                    suds_value = getattr(suds, key)
                    value_type = type(suds_value).__name__
                    
                    # Try to get actual value
                    value_str = str(suds_value)[:40] if suds_value is not None else 'None'
                    
                    # Check if it's an enum
                    if 'EnumOptionId' in str(type(suds_value)):
                        value_type = 'EnumOptionId'
                        if hasattr(suds_value, 'id'):
                            value_str = suds_value.id
                    elif 'Array' in value_type:
                        value_type = f'{value_type} ({len(suds_value)} items)'
                        if suds_value and hasattr(suds_value, '__iter__'):
                            first = suds_value[0] if len(suds_value) > 0 else None
                            if first and hasattr(first, 'id'):
                                value_str = f'[{first.id}, ...]'
                    
                    print(f"{key:<35} | {value_type:<20} | {value_str:<40}")
                
                except Exception as e:
                    print(f"{key:<35} | {'error':<20} | {str(e)[:40]}")
        
        # Try the getCustomFieldKeys method (without "Defined")
        print("\n" + "=" * 80)
        print("USING getCustomFieldKeys METHOD")
        print("=" * 80)
        
        session = wi.session
        service = session.tracker_client.service
        
        try:
            custom_keys = service.getCustomFieldKeys(wi.uri)
            if custom_keys:
                print(f"\n✓ Found {len(custom_keys)} custom field keys:\n")
                for key in sorted(custom_keys):
                    print(f"  - {key}")
                    
                    # Try to get the value
                    try:
                        value = service.getCustomField(wi.uri, key)
                        print(f"    Value: {value}")
                    except Exception as e:
                        print(f"    Error reading: {e}")
            else:
                print("\n⚠ No custom field keys found")
        
        except Exception as e:
            print(f"\n✗ Error: {e}")
        
        # Try to check if there's custom fields in the project metadata
        print("\n" + "=" * 80)
        print("CHECKING SUDS METADATA")
        print("=" * 80)
        
        if hasattr(suds, '__metadata__'):
            metadata = suds.__metadata__
            print(f"\nMetadata type: {type(metadata)}")
            print(f"Metadata attributes: {dir(metadata)}")
            
            if hasattr(metadata, 'sxtype'):
                sxtype = metadata.sxtype
                print(f"\nType info: {sxtype}")
                
                if hasattr(sxtype, 'schema'):
                    print(f"Schema: {sxtype.schema}")
                
                if hasattr(sxtype, 'children'):
                    print(f"\nChild elements ({len(sxtype.children())}):")
                    for child in sxtype.children():
                        child_name = child[0] if isinstance(child, tuple) else str(child)
                        print(f"  - {child_name}")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    inspect_suds_object()

