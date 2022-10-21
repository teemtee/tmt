""" Click Context Object Container """

import dataclasses
from typing import Optional, Set

import tmt.utils


@dataclasses.dataclass
class ContextObject:
    """ Click Context Object Container """
    common: tmt.utils.Common
    fmf_context: tmt.utils.FmfContextType
    tree: tmt.Tree
    steps: Set[str] = dataclasses.field(default_factory=set)
    clean: Optional[tmt.Clean] = None
    run: Optional[tmt.Run] = None
