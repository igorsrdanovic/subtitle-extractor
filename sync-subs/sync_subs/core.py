"""Subtitle sync detection and correction using ffsubsync.

Usage
-----
Install the dependency first::

    pip install sync-subs

Then use the public helpers::

    from sync_subs.core import check_sync, fix_sync

    offset, confidence = check_sync(Path("video.mkv"), Path("sub.srt"))
    if abs(offset) > 0.5:
        fix_sync(Path("video.mkv"), Path("sub.srt"))
"""

import logging
import tempfile
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    from ffsubsync.ffsubsync import make_parser  # type: ignore[import]
    from ffsubsync.ffsubsync import run as _ffsubsync_run  # type: ignore[import]
    HAS_FFSUBSYNC = True
except ImportError:
    HAS_FFSUBSYNC = False


def check_sync(
    video_file: Path,
    subtitle_file: Path,
) -> Tuple[float, float]:
    """Detect the timing offset between *subtitle_file* and *video_file*.

    Uses ffsubsync's VAD (Voice Activity Detection) pipeline to compare the
    speech activity timeline in the audio against the subtitle on/off timeline,
    then reports the cross-correlation peak as the offset.

    Parameters
    ----------
    video_file:
        Path to the reference video (any format ffmpeg can read).
    subtitle_file:
        Path to the subtitle file to check (SRT or ASS).

    Returns
    -------
    ``(offset_seconds, confidence)`` where:

    - ``offset_seconds`` is positive when subtitles are **late**,
      negative when they are **early**.
    - ``confidence`` is between 0.0 and 1.0; higher means more reliable.

    Returns ``(0.0, 0.0)`` when ffsubsync is not installed or on any error.
    """
    if not HAS_FFSUBSYNC:
        return 0.0, 0.0

    suffix = subtitle_file.suffix or ".srt"
    tmp_path = Path(tempfile.mktemp(suffix=suffix))
    try:
        parser = make_parser()
        args = parser.parse_args([
            str(video_file),
            "-i", str(subtitle_file),
            "-o", str(tmp_path),
        ])
        result = _ffsubsync_run(args)

        offset = float(result.get("offset_seconds", 0.0))
        sync_ok = bool(result.get("sync_was_successful", False))
        # ffsubsync does not expose a numeric confidence score directly.
        # We use a high proxy (0.9) when the run was successful and a low
        # proxy (0.2) when the internal correlation did not converge.
        confidence = 0.9 if sync_ok else 0.2

        return offset, confidence

    except Exception as exc:
        logger.debug("ffsubsync check failed: %s", exc)
        return 0.0, 0.0

    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def fix_sync(video_file: Path, subtitle_file: Path) -> bool:
    """Detect the timing offset and rewrite *subtitle_file* in place.

    Writes corrected timestamps to a temporary file first; only replaces the
    original when the operation succeeds so the source is never left in a
    corrupt state.

    Parameters
    ----------
    video_file:
        Path to the reference video.
    subtitle_file:
        Path to the subtitle file to correct (modified in place on success).

    Returns
    -------
    ``True`` on success, ``False`` on failure or when ffsubsync is not installed.
    """
    if not HAS_FFSUBSYNC:
        return False

    suffix = subtitle_file.suffix or ".srt"
    tmp_path = Path(tempfile.mktemp(suffix=suffix))
    try:
        parser = make_parser()
        args = parser.parse_args([
            str(video_file),
            "-i", str(subtitle_file),
            "-o", str(tmp_path),
        ])
        result = _ffsubsync_run(args)

        if result.get("retval", 1) == 0 and tmp_path.exists():
            # Atomically replace original with corrected version.
            tmp_path.replace(subtitle_file)
            return True

        return False

    except Exception as exc:
        logger.debug("ffsubsync fix failed: %s", exc)
        return False

    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
