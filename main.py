"""web-search v1.0.0 · System web-research extension — entry point (SDK 5.x / SDL)."""
from __future__ import annotations

import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir in sys.path:
    sys.path.remove(_dir)
sys.path.insert(0, _dir)

for _m in list(sys.modules):
    if _m in ("app", "backend", "schemas_sdl", "schemas_sdl_builders",
              "handlers_search", "skeleton"):
        del sys.modules[_m]

from app import ext, chat    # noqa: F401

# SDL entity classes must be importable before any handler that uses them.
import schemas_sdl            # noqa: F401
import schemas_sdl_builders   # noqa: F401

import backend                # noqa: F401
import handlers_search        # noqa: F401
import skeleton               # noqa: F401
