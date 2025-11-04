#!/usr/bin/env python3
"""
List all available methods in the Polarion SOAP service
"""

def list_service_methods():
    from pylero.work_item import _WorkItem
    
    project_id = 'RHELCockpit'
    work_item_id = 'RHELCOCKPIT-710'
    
    print("=" * 80)
    print("POLARION SERVICE METHODS")
    print("=" * 80)
    
    try:
        wi = _WorkItem(project_id=project_id, work_item_id=work_item_id)
        session = wi.session
        
        # Check tracker service
        print("\n🔧 TRACKER SERVICE METHODS:")
        print("-" * 80)
        client = session.tracker_client
        service = client.service
        
        # Get methods from the WSDL
        port = client.wsdl.services[0].ports[0]
        methods = []
        for method in port.methods.values():
            methods.append(method.name)
        print(f"Found {len(methods)} methods\n")
        
        # Categorize methods
        enum_methods = [m for m in methods if 'enum' in m.lower()]
        field_methods = [m for m in methods if 'field' in m.lower() or 'custom' in m.lower()]
        workitem_methods = [m for m in methods if 'workitem' in m.lower()]
        
        if enum_methods:
            print("📌 ENUM-RELATED METHODS:")
            for m in sorted(enum_methods):
                print(f"  - {m}")
        
        if field_methods:
            print("\n📌 FIELD/CUSTOM-RELATED METHODS:")
            for m in sorted(field_methods):
                print(f"  - {m}")
        
        if workitem_methods:
            print("\n📌 WORK ITEM-RELATED METHODS:")
            for m in sorted(workitem_methods)[:15]:  # First 15
                print(f"  - {m}")
            if len(workitem_methods) > 15:
                print(f"  ... and {len(workitem_methods) - 15} more")
        
        print(f"\n💡 ALL {len(methods)} METHODS:")
        print("-" * 80)
        for idx, m in enumerate(sorted(methods), 1):
            print(f"{idx:3d}. {m}")
        
        # Try project service
        print("\n" + "=" * 80)
        print("🔧 PROJECT SERVICE METHODS:")
        print("=" * 80)
        
        try:
            project_client = session.project_client
            port = project_client.wsdl.services[0].ports[0]
            project_methods = []
            for method in port.methods.values():
                project_methods.append(method.name)
            print(f"Found {len(project_methods)} methods\n")
            
            for idx, m in enumerate(sorted(project_methods), 1):
                print(f"{idx:3d}. {m}")
        except AttributeError as e:
            print(f"⚠ Project service not available: {e}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    list_service_methods()

