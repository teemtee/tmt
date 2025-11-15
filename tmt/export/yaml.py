import tmt.base.core
import tmt.export
import tmt.utils


@tmt.base.core.FmfId.provides_export('yaml')
@tmt.base.core.Test.provides_export('yaml')
@tmt.base.Plan.provides_export('yaml')
@tmt.base.core.Story.provides_export('yaml')
class YAMLExporter(tmt.export.TrivialExporter):
    @classmethod
    def _export(cls, data: tmt.export._RawExported) -> str:
        return tmt.utils.dict_to_yaml(data)
