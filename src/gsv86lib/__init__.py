"""
gsv86lib package

Thin wrapper around the original ME-Systeme gsv8pypi_python3 modules.

Typical usage in your projects:

    from gsv86lib import gsv86

    # or, if you want to import directly from the public API of gsv86.py:
    from gsv86lib import SomeClassOrFunction   # if defined in gsv86.py

"""

# Re-export everything from gsv86.py that does not start with "_"
from .gsv86 import *  # noqa: F401,F403

# Optional: define __all__ to control what "from gsv86lib import *" exports
__all__ = [name for name in globals().keys() if not name.startswith("_")]