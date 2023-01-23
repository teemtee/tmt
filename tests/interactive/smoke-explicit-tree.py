#!/usr/bin/env python3

import tmt
from tmt.utils import Path

tree = tmt.Tree.grow(path=Path.cwd() / "data")
print("\n".join(plan.name for plan in tree.plans()))
