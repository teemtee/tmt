import tmt.base
import tmt.export
import tmt.utils


@tmt.base.FmfId.provides_export('yaml')
@tmt.base.Test.provides_export('yaml')
@tmt.base.Plan.provides_export('yaml')
@tmt.base.Story.provides_export('yaml')
class YAMLExporter(tmt.export.TrivialExporter):
    @classmethod
    def _export(cls, data: tmt.export._RawExported) -> str:
        return tmt.utils.dict_to_yaml(data)
