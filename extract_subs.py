#!/usr/bin/env python3
"""
Video Subtitle Extractor — backward-compatibility shim.

The actual implementation now lives in the ``subtitle_extractor`` package.
This file is kept so that users who invoke ``python extract_subs.py ...``
continue to work without changes.

New installation method::

    pip install -e .
    subtitle-extractor /path/to/videos --languages en es

Or::

    python -m subtitle_extractor /path/to/videos --languages en es
"""

from subtitle_extractor.cli import main  # noqa: F401

if __name__ == "__main__":
    main()
