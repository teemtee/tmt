import tmt.base.core
import tmt.base.plan
import tmt.export
import tmt.utils


@tmt.base.core.FmfId.provides_export('yaml')
@tmt.base.core.Test.provides_export('yaml')
@tmt.base.plan.Plan.provides_export('yaml')
@tmt.base.core.Story.provides_export('yaml')
class YAMLExporter(tmt.export.TrivialExporter):
    @classmethod
    def _export(cls, data: tmt.export._RawExported) -> str:
        return tmt.utils.to_yaml(data)
