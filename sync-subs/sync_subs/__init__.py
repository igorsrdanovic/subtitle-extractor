"""sync-subs: automatically detect and fix subtitle timing offset."""

from .core import HAS_FFSUBSYNC, check_sync, fix_sync

__all__ = ["check_sync", "fix_sync", "HAS_FFSUBSYNC"]
__version__ = "0.1.0"
