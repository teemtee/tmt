import json

import tmt.base
import tmt.export
import tmt.utils


@tmt.base.FmfId.provides_export('json')
@tmt.base.Test.provides_export('json')
@tmt.base.Plan.provides_export('json')
@tmt.base.Story.provides_export('json')
class JSONExporter(tmt.export.TrivialExporter):
    @classmethod
    def _export(cls, data: tmt.export._RawExported) -> str:
        return json.dumps(data)
