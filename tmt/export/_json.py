import json

import tmt.base.core
import tmt.export


@tmt.base.core.FmfId.provides_export('json')
@tmt.base.core.Test.provides_export('json')
@tmt.base.core.Plan.provides_export('json')
@tmt.base.core.Story.provides_export('json')
class JSONExporter(tmt.export.TrivialExporter):
    @classmethod
    def _export(cls, data: tmt.export._RawExported) -> str:
        return json.dumps(data)
