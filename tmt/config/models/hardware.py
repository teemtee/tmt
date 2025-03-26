from tmt.container import MetadataContainer


class MrackTranslation(MetadataContainer):
    """
    Here's a full config example:

    .. code-block:: yaml

     beaker:
       translations:
         - requirement: cpu.processors
           template: '{"cpu": {"processors": {"_op": "{{ OPERATOR }}", "_value": "{{ VALUE }}"}}}'

    """

    requirement: str
    template: str


class MrackHardware(MetadataContainer):
    translations: list[MrackTranslation]


class HardwareConfig(MetadataContainer):
    beaker: MrackHardware
