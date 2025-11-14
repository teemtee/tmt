import tmt.base.core
import tmt.export
import tmt.utils


@tmt.base.core.FmfId.provides_export('dict')
@tmt.base.core.Test.provides_export('dict')
@tmt.base.core.Plan.provides_export('dict')
@tmt.base.core.Story.provides_export('dict')
class DictExporter(tmt.export.TrivialExporter):
    @classmethod
    def _export(cls, data: tmt.export._RawExported) -> str:
        return str(data)
