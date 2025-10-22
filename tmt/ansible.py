"""
Ansible integration for tmt.

This module provides classes and utilities for managing Ansible inventory generation
and configuration within tmt test plans.
"""

from typing import TYPE_CHECKING, Any, Optional, cast

from typing_extensions import TypedDict

import tmt.log
import tmt.utils
from tmt._compat.pathlib import Path
from tmt.container import SerializableContainer, container, field

if TYPE_CHECKING:
    from tmt.steps.provision import Guest


class _RawGuestAnsible(TypedDict, total=False):
    """Raw input data for GuestAnsible.from_spec()"""

    group: Optional[str]
    vars: Optional[dict[str, Any]]


class _RawPlanAnsibleInventory(TypedDict, total=False):
    """Raw input data for PlanAnsibleInventory.from_spec()"""

    layout: Optional[str]


def normalize_plan_ansible(
    key_address: str,
    raw_ansible: Any,
    logger: tmt.log.Logger,
) -> 'PlanAnsible':
    """
    Normalize a ``ansible`` key value.

    :param key_address: location of the key being that's being normalized.
    :param logger: logger to use for logging.
    :param raw_ansible: input from either command line or fmf node.
    """

    if isinstance(raw_ansible, PlanAnsible):
        return raw_ansible

    return PlanAnsible.from_spec(raw_ansible)


def normalize_guest_ansible(
    key_address: str,
    raw_ansible: Any,
    logger: tmt.log.Logger,
) -> 'GuestAnsible':
    """
    Normalize a ``ansible`` key value from provision guest data.

    :param key_address: location of the key being that's being normalized.
    :param logger: logger to use for logging.
    :param raw_ansible: input from either command line or fmf node.
    """

    if isinstance(raw_ansible, GuestAnsible):
        return raw_ansible

    return GuestAnsible.from_spec(raw_ansible)


@container
class GuestAnsible(SerializableContainer):
    """
    Ansible configuration for individual guests.
    """

    group: Optional[str] = field(
        default=None,
        help='Assigns the guest to a specific Ansible group.',
    )
    # TODO Add typing for vars raw input data
    vars: dict[str, Any] = field(  # pyright: ignore[reportUnknownVariableType]
        default_factory=dict,
        help=(
            'Defines host-specific Ansible variables to include under that host in the inventory.'
        ),
    )

    @classmethod
    def from_spec(cls, spec: Optional[_RawGuestAnsible]) -> 'GuestAnsible':
        """
        Convert a YAML mapping into GuestAnsible object.
        """
        if spec is None:
            return cls()

        return cls(**spec)  # type: ignore[arg-type]

    def to_spec(self) -> _RawGuestAnsible:
        """
        Convert GuestAnsible object to a YAML-serializable specification.
        """
        spec_dict = self.to_dict()

        if not self.group:
            spec_dict.pop('group', None)
        if not self.vars:
            spec_dict.pop('vars', None)

        return cast(_RawGuestAnsible, spec_dict)


@container
class PlanAnsibleInventory(SerializableContainer):
    """
    Ansible inventory configuration for the plan.
    """

    layout: Optional[str] = field(
        default=None,
        help='Path to a YAML file defining the inventory group hierarchy and layout.',
    )

    @classmethod
    def from_spec(cls, spec: Optional[_RawPlanAnsibleInventory]) -> 'PlanAnsibleInventory':
        """
        Convert a YAML mapping into PlanAnsibleInventory object.
        """
        if spec is None:
            return cls()

        return cls(**spec)

    def to_spec(self) -> _RawPlanAnsibleInventory:
        """
        Convert PlanAnsibleInventory object to a YAML-serializable specification.
        """
        spec_dict = self.to_dict()

        if not self.layout:
            spec_dict.pop('layout', None)

        return cast(_RawPlanAnsibleInventory, spec_dict)


@container
class PlanAnsible(SerializableContainer):
    """
    Root level general Ansible configuration
    """

    inventory: Optional[PlanAnsibleInventory] = field(
        default=None,
        help='Inventory configuration for the plan.',
        serialize=lambda inventory: inventory.to_serialized() if inventory else None,
        unserialize=lambda serialized: PlanAnsibleInventory.from_serialized(serialized)  # pyright: ignore[reportArgumentType]
        if serialized
        else None,
    )

    @classmethod
    def from_spec(cls, spec: Any) -> 'PlanAnsible':
        """
        Convert a YAML mapping into PlanAnsible object.
        """
        if spec is None:
            return cls()

        if isinstance(spec, cls):
            return spec

        if isinstance(spec, dict):
            inventory_spec = cast(Optional[_RawPlanAnsibleInventory], spec.get('inventory'))
            if inventory_spec is not None:
                spec = cast(dict[str, Any], spec.copy())
                spec['inventory'] = PlanAnsibleInventory.from_spec(inventory_spec)

            return cls(**spec)  # pyright: ignore[reportUnknownArgumentType]

        raise tmt.utils.SpecificationError(f"Invalid Ansible specification: {spec}")

    def to_spec(self) -> dict[str, Any]:
        """
        Convert PlanAnsible object to a YAML-serializable specification.
        """
        spec: dict[str, Any] = {}

        if self.inventory is not None:
            spec['inventory'] = self.inventory.to_spec()

        return spec


class AnsibleInventory:
    """
    Generate Ansible inventory files from provisioned guests.

    Creates Ansible inventory file that can be used with playbooks
    to manage provisioned guests. Supports custom layouts and automatically
    configures host variables based on guest properties.
    """

    @classmethod
    def _load_layout(cls, layout_path: Optional[Path] = None) -> dict[str, Any]:
        """
        Load inventory layout from file or use default, ensuring required Ansible structure.

        :param layout_path: full path to a custom layout file.
        :returns: dictionary representing the inventory layout structure with required groups.
        """
        if layout_path:
            try:
                layout = tmt.utils.yaml_to_dict(layout_path.read_text())
            except (OSError, FileNotFoundError):
                raise tmt.utils.FileError(f"Inventory layout file '{layout_path}' not found")
        else:
            layout = {}

        return cls._normalize_layout(layout)

    @classmethod
    def _normalize_layout(cls, layout: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize layout to ensure required Ansible inventory structure.

        Ensures 'all' and 'ungrouped' groups are present.

        :param layout: raw layout dictionary from file or empty dict.
        :returns: normalized inventory with required Ansible structure.
        """
        # Ensure 'all' group exists
        if 'all' not in layout:
            layout['all'] = {}

        # Ensure 'ungrouped' exists for hosts without explicit groups
        if 'children' not in layout['all']:
            layout['all']['children'] = {}
        if 'ungrouped' not in layout['all']['children']:
            layout['all']['children']['ungrouped'] = {}

        return layout

    @classmethod
    def _add_host_to_all(cls, inventory: dict[str, Any], guest: 'Guest') -> None:
        """
        Add host with its variables to the 'all' group.

        :param inventory: the inventory dictionary to modify.
        :param guest: the guest to add to the inventory.
        """
        if 'hosts' not in inventory['all']:
            inventory['all']['hosts'] = {}
        inventory['all']['hosts'][guest.name] = guest.ansible_host_vars

    @classmethod
    def _find_group(cls, current: dict[str, Any], target: str) -> Optional[dict[str, Any]]:
        """
        Find a group at any level in the hierarchy.

        :param current: the current level of the inventory hierarchy.
        :param target: the name of the group to find.
        :returns: the group dictionary if found, ``None`` otherwise.
        """
        if target in current:
            return current[target]  # type: ignore[no-any-return]
        for value in current.values():
            if isinstance(value, dict) and 'children' in value:
                found = cls._find_group(value['children'], target)  # pyright: ignore[reportUnknownArgumentType]
                if found is not None:
                    return found
        return None

    @classmethod
    def _add_host_to_group(cls, inventory: dict[str, Any], guest: 'Guest', group: str) -> None:
        """
        Add host to a specific group without variables.

        :param inventory: the inventory dictionary to modify.
        :param guest: the guest to add to the group.
        :param group: the name of the group to add the host to.
        """
        if group == 'all':
            return

        target_group = cls._find_group(inventory['all']['children'], group)
        if target_group is None:
            # Group not found, create it at the root level
            if group not in inventory['all']['children']:
                inventory['all']['children'][group] = {'hosts': {}}
            target_group = inventory['all']['children'][group]

        if 'hosts' not in target_group:
            target_group['hosts'] = {}
        target_group['hosts'][guest.name] = {}

    @classmethod
    def generate(cls, guests: list['Guest'], layout_path: Optional[Path] = None) -> dict[str, Any]:
        """
        Generate Ansible inventory from guests and layout.

        :param guests: list of provisioned guests to include in the inventory.
        :param layout_path: optional full path to a custom layout template.
        :returns: complete Ansible inventory dictionary.
        """
        inventory = cls._load_layout(layout_path)

        for guest in guests:
            # Add host to 'all' group with its variables
            cls._add_host_to_all(inventory, guest)

            # Add host to its groups (without variables)
            for group in guest.ansible_host_groups:
                cls._add_host_to_group(inventory, guest, group)

        return inventory
