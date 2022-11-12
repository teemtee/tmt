from typing import Any, List, Optional

import tmt.base
import tmt.export
import tmt.utils


@tmt.base.FmfId.provides_export('dict')
@tmt.base.Test.provides_export('dict')
@tmt.base.Plan.provides_export('dict')
@tmt.base.Story.provides_export('dict')
class DictExporter(tmt.export.ExportPlugin):
    @classmethod
    def _export(cls, data: tmt.export._RawExported) -> str:
        return str(data)

    @classmethod
    def export_fmfid_collection(cls,
                                fmf_ids: List[tmt.base.FmfId],
                                keys: Optional[List[str]] = None,
                                **kwargs: Any) -> str:
        return cls._export([fmf_id._export(keys=keys) for fmf_id in fmf_ids])

    @classmethod
    def export_test_collection(cls,
                               tests: List[tmt.base.Test],
                               keys: Optional[List[str]] = None,
                               **kwargs: Any) -> str:
        return cls._export([test._export(keys=keys) for test in tests])

    @classmethod
    def export_plan_collection(cls,
                               plans: List[tmt.base.Plan],
                               keys: Optional[List[str]] = None,
                               **kwargs: Any) -> str:
        return cls._export([plan._export(keys=keys) for plan in plans])

    @classmethod
    def export_story_collection(cls,
                                stories: List[tmt.base.Story],
                                keys: Optional[List[str]] = None,
                                **kwargs: Any) -> str:
        return cls._export([story._export(keys=keys) for story in stories])
