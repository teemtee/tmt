#!/usr/bin/env python3

import tmt

tree = tmt.Tree.grow()
print("\n".join(plan.name for plan in tree.plans()))
