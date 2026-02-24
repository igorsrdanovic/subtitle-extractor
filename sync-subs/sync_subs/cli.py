"""Command-line interface for sync-subs.

Usage
-----
::

    sync-subs video.mkv subtitle.srt          # detect and fix in-place
    sync-subs video.mkv subtitle.srt --check  # report offset only
    sync-subs video.mkv subtitle.srt --output fixed.srt
    sync-subs video.mkv subtitle.srt --threshold 0.3 --verbose
"""

import argparse
import shutil
import sys
from pathlib import Path

from .core import HAS_FFSUBSYNC, check_sync, fix_sync

_CONFIDENCE_LOW = 0.3
_DEFAULT_THRESHOLD = 0.5


def _fmt_offset(offset: float) -> str:
    sign = "+" if offset >= 0 else ""
    return f"{sign}{offset:.2f} s"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sync-subs",
        description=(
            "Automatically detect and fix subtitle timing offset.\n\n"
            "By default the subtitle file is corrected in place. Use --check\n"
            "to inspect without modifying, or --output to write to a new file."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", metavar="VIDEO", type=Path,
                        help="Reference video file (mkv, mp4, avi, …)")
    parser.add_argument("subtitle", metavar="SUBTITLE", type=Path,
                        help="Subtitle file to check/fix (srt, ass)")
    parser.add_argument("--check", "-c", action="store_true",
                        help="Report offset only; do not modify the subtitle file")
    parser.add_argument("--output", "-o", metavar="PATH", type=Path,
                        help="Write corrected subtitle here instead of in-place")
    parser.add_argument("--threshold", "-t", metavar="N", type=float,
                        default=_DEFAULT_THRESHOLD,
                        help="Minimum offset in seconds to report/fix (default: 0.5)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show confidence score in output")

    args = parser.parse_args()

    # --- pre-flight checks ---------------------------------------------------

    if not HAS_FFSUBSYNC:
        print(
            "Error: ffsubsync is not installed.\n"
            "Install it with:  pip install ffsubsync",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.video.exists():
        print(f"Error: video file not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    if not args.subtitle.exists():
        print(f"Error: subtitle file not found: {args.subtitle}", file=sys.stderr)
        sys.exit(1)

    if args.threshold < 0:
        print("Error: --threshold must be >= 0", file=sys.stderr)
        sys.exit(1)

    # --check and --output are mutually exclusive
    if args.check and args.output:
        print("Error: --check and --output cannot be used together", file=sys.stderr)
        sys.exit(1)

    # --- detect offset -------------------------------------------------------

    offset, confidence = check_sync(args.video, args.subtitle)

    confidence_note = f"  [confidence: {confidence:.2f}]" if args.verbose else ""
    in_sync = abs(offset) < args.threshold
    low_confidence = confidence < _CONFIDENCE_LOW

    if low_confidence:
        print(
            f"? Uncertain  (offset: {_fmt_offset(offset)}){confidence_note}\n"
            f"  Low confidence — the audio may be music-heavy or dialogue-sparse.",
            file=sys.stderr,
        )
        sys.exit(0)

    if in_sync:
        print(f"OK In sync   (offset: {_fmt_offset(offset)}){confidence_note}")
        sys.exit(0)

    # offset is above threshold -----------------------------------------------

    if args.check:
        direction = "late" if offset > 0 else "early"
        print(
            f"!! Offset    {_fmt_offset(offset)} ({direction}){confidence_note}\n"
            f"   Run without --check to fix automatically."
        )
        sys.exit(2)

    # --- fix -----------------------------------------------------------------

    # Determine the target file for fix_sync (which always writes in-place).
    if args.output:
        # Copy to output path first, then fix the copy.
        shutil.copy2(args.subtitle, args.output)
        target = args.output
    else:
        target = args.subtitle

    success = fix_sync(args.video, target)

    if success:
        location = f"-> {target}" if args.output else "(in place)"
        print(f"OK Fixed     (offset: {_fmt_offset(offset)} corrected) {location}{confidence_note}")
        sys.exit(0)
    else:
        print(
            f"Error: sync correction failed for {args.subtitle}",
            file=sys.stderr,
        )
        # Clean up the copy if we created one and it failed.
        if args.output and args.output.exists():
            args.output.unlink()
        sys.exit(1)


if __name__ == "__main__":
    main()
