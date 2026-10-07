#!/usr/bin/env python3
# Dependencies must match the uv.lock
import shutil
from pathlib import Path

from sphinx.cmd.build import main as sphinx_build

ROOT_DIR = Path(__file__).parent.parent
DOC_DIR = ROOT_DIR / "docs"
DOC_BUILD_DIR = DOC_DIR / "_build"

ret = sphinx_build(
    [
        str(DOC_DIR),
        str(DOC_BUILD_DIR),
        "-b",
        "man",
    ]
)

if ret:
    raise SystemExit(ret)

for man_file in DOC_BUILD_DIR.glob("*.1"):
    shutil.copy(man_file, DOC_DIR)
