"""
Ansible integration for tmt.

This module provides classes and utilities for managing Ansible inventory generation
and configuration within tmt test plans.
"""

from typing import TYPE_CHECKING, Any, Optional

import tmt.log
import tmt.utils
from tmt.container import SerializableContainer, container, field

if TYPE_CHECKING:
    from tmt.steps.provision import Guest


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
    return GuestAnsible.from_spec(raw_ansible)


def normalize_plan_ansible_inventory(
    key_address: str,
    raw_inventory: Any,
    logger: tmt.log.Logger,
) -> Optional['PlanAnsibleInventory']:
    """
    Normalize a ``inventory`` key value.

    :param key_address: location of the key being that's being normalized.
    :param logger: logger to use for logging.
    :param raw_inventory: input from either command line or fmf node.
    """
    if raw_inventory is None:
        return None

    return PlanAnsibleInventory.from_spec(raw_inventory)


@container
class GuestAnsible(SerializableContainer):
    """
    Ansible configuration for individual guests.
    """

    group: Optional[str] = field(
        default=None,
        help='Assigns the guest to a specific Ansible group.',
    )
    vars: dict[str, Any] = field(  # pyright: ignore[reportUnknownVariableType]
        default_factory=dict,
        help=(
            'Defines host-specific Ansible variables to include under that host in the inventory.'
        ),
    )

    @classmethod
    def from_spec(cls, spec: Any) -> 'GuestAnsible':
        """
        Convert a YAML mapping into GuestAnsible object.
        """
        if spec is None:
            return cls()

        if isinstance(spec, cls):
            return spec

        if isinstance(spec, dict):
            return cls(**spec)  # pyright: ignore[reportUnknownArgumentType]

        raise tmt.utils.SpecificationError(f"Invalid Ansible specification: {spec}")

    def to_spec(self) -> dict[str, Any]:
        """
        Convert GuestAnsible object to a YAML-serializable specification.
        """
        spec: dict[str, Any] = {}

        if self.group is not None:
            spec['group'] = self.group

        if self.vars:
            spec['vars'] = self.vars

        return spec


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
    def from_spec(cls, spec: Any) -> 'PlanAnsibleInventory':
        """
        Convert a YAML mapping into PlanAnsibleInventory object.
        """
        if spec is None:
            return cls()

        if isinstance(spec, cls):
            return spec

        if isinstance(spec, dict):
            return cls(**spec)  # pyright: ignore[reportUnknownArgumentType]

        raise tmt.utils.SpecificationError(f"Invalid Ansible inventory specification: {spec}")

    def to_spec(self) -> dict[str, Any]:
        """
        Convert PlanAnsibleInventory object to a YAML-serializable specification.
        """
        spec: dict[str, Any] = {}

        if self.layout is not None:
            spec['layout'] = self.layout

        return spec

    def __repr__(self) -> str:
        """Return a string representation of the PlanAnsibleInventory object."""
        return f"PlanAnsibleInventory(layout={self.layout})"


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
            inventory_spec = spec.get('inventory')  # pyright: ignore[reportUnknownVariableType]
            if inventory_spec is not None:
                spec = spec.copy()  # pyright: ignore[reportUnknownVariableType]
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

    def __repr__(self) -> str:
        """Return a string representation of the PlanAnsible object."""
        return f"PlanAnsible(inventory={self.inventory})"


class AnsibleInventory:
    """
    Generate Ansible inventory files from provisioned guests.

    Creates Ansible inventory file that can be used with playbooks
    to manage provisioned guests. Supports custom layouts and automatically
    configures host variables based on guest properties.
    """

    def __init__(self, plan: 'tmt.Plan') -> None:
        """
        Initialize the Ansible inventory handler.

        :param plan: the plan containing provisioned guests and configuration.
        """
        self._logger = plan._logger
        self._plan = plan

    def _load_layout(self, layout_path: Optional[str] = None) -> dict[str, Any]:
        """
        Load inventory layout from file or use default.

        :param layout_path: path to a custom layout file, relative to the metadata tree root,
                            or to the current working directory.
        :returns: dictionary representing the inventory layout structure.
        """
        if layout_path:
            resolved_path = self._plan.anchor_path / layout_path
            try:
                return tmt.utils.yaml_to_dict(resolved_path.read_text())
            except (OSError, FileNotFoundError):
                raise tmt.utils.FileError(f"Inventory layout file '{layout_path}' not found")

        return self._default_layout()

    def _default_layout(self) -> dict[str, Any]:
        """
        Create default inventory layout.

        :returns: basic inventory structure with 'all' and 'ungrouped' groups.
        """
        return {'all': {'children': {'ungrouped': {}}}}

    def _add_host_to_all(self, inventory: dict[str, Any], guest: 'Guest') -> None:
        """
        Add host with its variables to the 'all' group.

        :param inventory: the inventory dictionary to modify.
        :param guest: the guest to add to the inventory.
        """
        host_vars = guest.ansible_host_vars
        if 'hosts' not in inventory['all']:
            inventory['all']['hosts'] = {}
        inventory['all']['hosts'][guest.name] = host_vars

    def _find_group(self, current: dict[str, Any], target: str) -> Optional[dict[str, Any]]:
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
                found = self._find_group(value['children'], target)  # pyright: ignore[reportUnknownArgumentType]
                if found is not None:
                    return found
        return None

    def _add_host_to_group(self, inventory: dict[str, Any], guest: 'Guest', group: str) -> None:
        """
        Add host to a specific group without variables.

        :param inventory: the inventory dictionary to modify.
        :param guest: the guest to add to the group.
        :param group: the name of the group to add the host to.
        """
        if group == 'all':
            return

        target_group = self._find_group(inventory['all']['children'], group)
        if target_group is None:
            # Group not found, create it at the root level
            if group not in inventory['all']['children']:
                inventory['all']['children'][group] = {'hosts': {}}
            target_group = inventory['all']['children'][group]

        if 'hosts' not in target_group:
            target_group['hosts'] = {}
        target_group['hosts'][guest.name] = {}

    def generate(self, guests: list['Guest'], layout_path: Optional[str] = None) -> dict[str, Any]:
        """
        Generate Ansible inventory from guests and layout.

        :param guests: list of provisioned guests to include in the inventory.
        :param layout_path: optional path to a custom layout template.
        :returns: complete Ansible inventory dictionary.
        """
        inventory = self._load_layout(layout_path)

        for guest in guests:
            # Add host to 'all' group with its variables
            self._add_host_to_all(inventory, guest)

            # Add host to its groups (without variables)
            groups = guest.ansible_host_groups
            for group in groups:
                self._add_host_to_group(inventory, guest, group)

        return inventory
