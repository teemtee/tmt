import tmt.base
import tmt.export
import tmt.utils


@tmt.base.FmfId.provides_export('dict')
@tmt.base.Test.provides_export('dict')
@tmt.base.Plan.provides_export('dict')
@tmt.base.Story.provides_export('dict')
class DictExporter(tmt.export.TrivialExporter):
    @classmethod
    def _export(cls, data: tmt.export._RawExported) -> str:
        return str(data)
