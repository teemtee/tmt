from tmt.container import MetadataContainer


class Translate(MetadataContainer):
    name: str
    template: str


class HardwareConfig(MetadataContainer):
    translations: list[Translate]
