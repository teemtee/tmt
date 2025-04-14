from tmt.config.models.hardware import HardwareConfig
from tmt.container import MetadataContainer


class DefaultConfig(MetadataContainer):
    hardware: HardwareConfig
