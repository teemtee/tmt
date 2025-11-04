#!/usr/bin/env python3
"""
Verify custom fields are actually set in Polarion
"""

from pylero.work_item import _WorkItem

project_id = 'RHELCockpit'
work_item_id = 'RHELCOCKPIT-710'

print("=" * 80)
print("VERIFYING CUSTOM FIELDS IN POLARION")
print("=" * 80)

wi = _WorkItem(project_id=project_id, work_item_id=work_item_id)
print(f"\n✓ Work item: {wi.work_item_id} - {wi.title}\n")

session = wi.session
service = session.tracker_client.service

# Get all custom field keys
custom_keys = service.getCustomFieldKeys(wi.uri)
print(f"Custom fields found: {len(custom_keys)}\n")

for key in sorted(custom_keys):
    try:
        result = service.getCustomField(wi.uri, key)
        if result and hasattr(result, 'value') and result.value:
            value_str = str(result.value)
            if hasattr(result.value, 'id'):
                value_str = f"{result.value.id} (Enum)"
            print(f"  ✓ {key:<30} = {value_str}")
        else:
            print(f"  ✗ {key:<30} = (not set)")
    except Exception as e:
        print(f"  ✗ {key:<30} = Error: {e}")

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
print("\nPlease also check in Polarion UI:")
print(f"https://polarion.engineering.redhat.com/polarion/#/project/{project_id}/workitem?id={work_item_id}")

