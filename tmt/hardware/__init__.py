"""
Guest hardware requirements specification and helpers.

tmt metadata allow to describe various HW requirements a guest needs to satisfy.
This package provides useful functions and classes for core functionality and
shared across provision plugins.

Parsing of HW requirements
==========================

Set of HW requirements, as given by test or plan metadata, is represented by
Python structures - lists, mappings, primitive types - when loaded from fmf
files. Part of the code below converts this representation to a tree of objects
that provide helpful operations for easier evaluation and processing of HW
requirements.

Each HW requirement "rule" in original metadata is a constraint, a condition
the eventual guest HW must satisfy. Each node of the tree created from HW
requirements is therefore called "a constraint", and represents either a single
condition ("trivial" constraints), or a set of such conditions plus a function
reducing their individual outcomes to one final answer for the whole set (think
:py:func:`any` and :py:func:`all` built-in functions) ("compound" constraints).
Components of each constraint - dimension, operator, value, units - are
decoupled from the rest, and made available for inspection.

[1] https://tmt.readthedocs.io/en/stable/spec/hardware.html
"""

from tmt.hardware.constraints import (
    UNITS,
    Constraint,
    FlagConstraint,
    IntegerConstraint,
    NumberConstraint,
    Operator,
    SizeConstraint,
    TextConstraint,
)
from tmt.hardware.requirements import Hardware

__all__ = [
    'UNITS',
    'Constraint',
    'FlagConstraint',
    'Hardware',
    'IntegerConstraint',
    'NumberConstraint',
    'Operator',
    'SizeConstraint',
    'TextConstraint',
]
