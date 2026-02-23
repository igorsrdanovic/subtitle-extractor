"""Command-line interface for subtitle-extractor."""

import logging
import sys
from pathlib import Path
from typing import Optional

from .config import load_config
from .extractor import SubtitleExtractor
from .utils import positive_int


# ------------------------------------------------------------------
# Logging setup (single, authoritative call)
# ------------------------------------------------------------------

def setup_logging(verbosity: int = 0, log_file: Optional[Path] = None) -> None:
    """Configure the root logger.

    Args:
        verbosity: -1 = WARNING only, 0 = INFO (default), 1 = DEBUG.
        log_file:  Optional path; when given, output goes to both file and stderr.
    """
    level = {-1: logging.WARNING, 0: logging.INFO, 1: logging.DEBUG}.get(
        verbosity, logging.INFO
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    fmt = "%(asctime)s - %(levelname)s - %(message)s" if log_file else "%(message)s"
    formatter = logging.Formatter(fmt)

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    root.addHandler(ch)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    """Parse arguments, validate inputs, and run extraction."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract subtitles from MKV, MP4, WebM, MOV, and AVI files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/tv/shows
  %(prog)s /path/to/movies --languages en es fr
  %(prog)s /path/to/videos --dry-run
  %(prog)s /path/to/videos --threads 4 --output-dir /path/to/subs
  %(prog)s /path/to/videos --convert-to srt --resume
  %(prog)s --clear-resume

Config file: create ~/.subtitle-extractor.yaml with default settings.
        """,
    )

    # ---- positional (optional so --clear-resume works without a directory) ----
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        help="Directory containing video files (searched recursively)",
    )

    # ---- language / filter ----
    parser.add_argument("-l", "--languages", nargs="+",
                        help="Language codes to extract (default: en)")
    parser.add_argument("--include-forced", action="store_true",
                        help="Include forced subtitles")
    parser.add_argument("--include-sdh", action="store_true",
                        help="Include SDH/hearing-impaired subtitles")
    parser.add_argument("--exclude-commentary", action="store_true",
                        help="Exclude commentary tracks")
    parser.add_argument("--track-title",
                        help="Filter by track title (case-insensitive substring match)")

    # ---- behaviour ----
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-extract even when subtitle files already exist")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be extracted without writing files")
    parser.add_argument("--threads", type=positive_int, default=1,
                        help="Number of parallel threads (default: 1)")
    parser.add_argument("--retries", type=int, default=0, metavar="N",
                        help="Retry failed extractions up to N times (default: 0)")
    parser.add_argument("--convert-to", choices=["srt", "ass"],
                        help="Convert all subtitles to the given format")
    parser.add_argument("--output-dir", type=Path,
                        help="Write subtitles to this directory")
    parser.add_argument("--preserve-structure", action="store_true",
                        help="Mirror source directory tree inside --output-dir")
    parser.add_argument("--resume", action="store_true",
                        help="Skip files already processed in a previous run")
    parser.add_argument("--clear-resume", action="store_true",
                        help="Delete the resume state file and exit")

    # ---- output / reporting ----
    parser.add_argument("--report-format", choices=["json", "csv"],
                        help="Write an extraction report in the given format")
    parser.add_argument("--log-file", type=Path,
                        help="Save log output to a file (in addition to stderr)")
    parser.add_argument("--list-tracks", action="store_true",
                        help="List all subtitle tracks without extracting (inspection mode)")

    # ---- sync detection ----
    parser.add_argument("--check-sync", action="store_true",
                        help="After extraction, report subtitle timing offset (non-destructive)")
    parser.add_argument("--fix-sync", action="store_true",
                        help="After extraction, detect and apply subtitle timing correction")
    parser.add_argument("--sync-threshold", type=float, default=0.5, metavar="N",
                        help="Minimum offset in seconds to report/fix (default: 0.5)")

    # ---- verbosity ----
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument("-v", "--verbose", action="store_true",
                                 help="Enable debug-level output")
    verbosity_group.add_argument("-q", "--quiet", action="store_true",
                                 help="Suppress informational messages (warnings and errors only)")

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Logging — single, correct setup before any other output
    # ------------------------------------------------------------------
    verbosity = 1 if args.verbose else (-1 if args.quiet else 0)
    setup_logging(verbosity=verbosity, log_file=args.log_file)

    # ------------------------------------------------------------------
    # --clear-resume: standalone action, no directory needed
    # ------------------------------------------------------------------
    if args.clear_resume:
        resume_file = Path.home() / ".subtitle-extractor-resume.pkl"
        if resume_file.exists():
            resume_file.unlink()
            print(f"Cleared resume state: {resume_file}")
        else:
            print("No resume state file found.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Directory is required for all other modes
    # ------------------------------------------------------------------
    if args.directory is None:
        parser.error("the following arguments are required: directory")

    if not args.directory.exists():
        print(f"Error: directory does not exist: {args.directory}", file=sys.stderr)
        sys.exit(1)
    if not args.directory.is_dir():
        print(f"Error: not a directory: {args.directory}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Load and merge config
    # ------------------------------------------------------------------
    config = load_config()

    languages = args.languages or config.get("languages", ["en"])
    overwrite = args.overwrite or config.get("overwrite", False)
    dry_run = args.dry_run or config.get("dry_run", False)
    threads = (
        args.threads
        if args.threads != parser.get_default("threads")
        else config.get("threads", 1)
    )
    retries = args.retries if args.retries != 0 else config.get("retries", 0)
    output_dir = args.output_dir or (
        Path(config["output_dir"]) if "output_dir" in config else None
    )
    preserve_structure = args.preserve_structure or config.get("preserve_structure", False)
    convert_to = args.convert_to or config.get("convert_to")
    check_sync = args.check_sync or config.get("check_sync", False)
    fix_sync = args.fix_sync or config.get("fix_sync", False)
    sync_threshold = (
        args.sync_threshold
        if args.sync_threshold != parser.get_default("sync_threshold")
        else config.get("sync_threshold", 0.5)
    )

    # ------------------------------------------------------------------
    # Tool availability checks
    # ------------------------------------------------------------------
    has_mkvtoolnix = SubtitleExtractor.check_mkvtoolnix()
    has_ffmpeg = SubtitleExtractor.check_ffmpeg()

    if not has_mkvtoolnix and not has_ffmpeg:
        print("Error: neither mkvtoolnix nor ffmpeg is installed.", file=sys.stderr)
        print("\nFor MKV support — install mkvtoolnix:", file=sys.stderr)
        print("  Ubuntu/Debian: sudo apt-get install mkvtoolnix", file=sys.stderr)
        print("  macOS:         brew install mkvtoolnix", file=sys.stderr)
        print("\nFor MP4 support — install ffmpeg:", file=sys.stderr)
        print("  Ubuntu/Debian: sudo apt-get install ffmpeg", file=sys.stderr)
        print("  macOS:         brew install ffmpeg", file=sys.stderr)
        sys.exit(1)

    if not has_mkvtoolnix:
        print("Warning: mkvtoolnix not found — MKV files will be skipped.", file=sys.stderr)
    if not has_ffmpeg:
        print("Warning: ffmpeg not found — MP4/WebM/MOV/AVI files will be skipped.", file=sys.stderr)
    if convert_to == "srt" and not SubtitleExtractor.check_pgsrip():
        print(
            "Warning: pgsrip not found — image-based subtitles (PGS/dvdsub) cannot be OCR'd.\n"
            "Install with: pip install pgsrip && apt install tesseract-ocr",
            file=sys.stderr,
        )

    if check_sync or fix_sync:
        from . import sync as sync_module  # noqa: PLC0415
        if not sync_module.HAS_FFSUBSYNC:
            print(
                "Warning: ffsubsync not installed — sync detection unavailable.\n"
                "Install with: pip install ffsubsync",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------
    # Create extractor instance
    # ------------------------------------------------------------------
    extractor = SubtitleExtractor(
        overwrite=overwrite,
        languages=languages,
        dry_run=dry_run,
        threads=threads,
        include_forced=args.include_forced,
        include_sdh=args.include_sdh,
        exclude_commentary=args.exclude_commentary,
        track_title=args.track_title,
        log_file=args.log_file,
        report_format=args.report_format,
        convert_to=convert_to,
        output_dir=output_dir,
        preserve_structure=preserve_structure,
        resume=args.resume,
        retries=retries,
        check_sync=check_sync,
        fix_sync=fix_sync,
        sync_threshold=sync_threshold,
    )

    logging.info(f"Extracting subtitles for: {', '.join(extractor.target_languages)}\n")

    # ------------------------------------------------------------------
    # Track inspection mode
    # ------------------------------------------------------------------
    if args.list_tracks:
        logging.info("=== TRACK INSPECTION MODE ===\n")
        directory = args.directory
        mkv_files = sorted(directory.rglob("*.mkv"))
        ffmpeg_files: list = []
        for ext in ("*.mp4", "*.webm", "*.mov", "*.avi"):
            ffmpeg_files.extend(directory.rglob(ext))
        video_files = sorted(mkv_files + sorted(ffmpeg_files))

        if not video_files:
            logging.info(f"No video files found in {directory}")
            sys.exit(0)

        logging.info(f"Found {len(video_files)} video file(s)\n")
        filter_parts = [f"Languages={', '.join(extractor.target_languages)}"]
        if args.include_forced:
            filter_parts.append("include forced")
        if args.include_sdh:
            filter_parts.append("include SDH")
        if args.exclude_commentary:
            filter_parts.append("exclude commentary")
        if args.track_title:
            filter_parts.append(f"title contains '{args.track_title}'")
        logging.info(f"Filters: {', '.join(filter_parts)}\n")

        for video_file in video_files:
            track_info = extractor.list_tracks_in_file(video_file)
            extractor.display_track_list(track_info)

        sys.exit(0)

    # ------------------------------------------------------------------
    # Normal extraction mode
    # ------------------------------------------------------------------
    extractor.process_directory(args.directory)
    extractor.print_summary()
