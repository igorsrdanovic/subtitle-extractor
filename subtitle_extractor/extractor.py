"""Core subtitle extraction logic."""

import csv
import json
import logging
import pickle
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class SubtitleExtractor:
    """Handles extraction of subtitles from MKV, MP4, WebM, MOV, and AVI files."""

    # Image-based subtitle codecs that require OCR for text conversion.
    IMAGE_BASED_CODECS: Set[str] = {
        "hdmv_pgs_subtitle", "pgssub", "hdmv pgs", "dvd_subtitle", "dvdsub",
        "vobsub", "dvbsub", "dvb_subtitle",
    }

    # Supported ffmpeg formats (non-MKV).
    FFMPEG_FORMATS: Set[str] = {".mp4", ".webm", ".mov", ".avi"}

    # Codec identifier → file extension.  Exact (case-insensitive) match is
    # attempted first; substring fallback is used for codec strings that embed
    # extra metadata (e.g. "SubRip/SRT").
    CODEC_EXTENSIONS: Dict[str, str] = {
        "subrip/srt": "srt",
        "subrip": "srt",
        "srt": "srt",
        "substationalpha": "ass",
        "ass": "ass",
        "ssa": "ass",
        "hdmv pgs": "sup",
        "vobsub": "sup",
        "hdmv_pgs_subtitle": "sup",
        "dvd_subtitle": "sup",
        "mov_text": "srt",
        "tx3g": "srt",
    }

    # Language code normalization mapping (ISO 639-2/T + full names → ISO 639-1).
    LANGUAGE_CODES: Dict[str, str] = {
        "eng": "en", "en": "en", "english": "en",
        "spa": "es", "es": "es", "spanish": "es",
        "fre": "fr", "fra": "fr", "fr": "fr", "french": "fr",
        "ger": "de", "deu": "de", "de": "de", "german": "de",
        "ita": "it", "it": "it", "italian": "it",
        "por": "pt", "pt": "pt", "portuguese": "pt",
        "rus": "ru", "ru": "ru", "russian": "ru",
        "jpn": "ja", "ja": "ja", "japanese": "ja",
        "chi": "zh", "zho": "zh", "zh": "zh", "chinese": "zh",
        "kor": "ko", "ko": "ko", "korean": "ko",
        "ara": "ar", "ar": "ar", "arabic": "ar",
        "hin": "hi", "hi": "hi", "hindi": "hi",
        "dut": "nl", "nld": "nl", "nl": "nl", "dutch": "nl",
        "pol": "pl", "pl": "pl", "polish": "pl",
        "swe": "sv", "sv": "sv", "swedish": "sv",
        "nor": "no", "no": "no", "norwegian": "no",
        "dan": "da", "da": "da", "danish": "da",
        "fin": "fi", "fi": "fi", "finnish": "fi",
        "tur": "tr", "tr": "tr", "turkish": "tr",
        "gre": "el", "ell": "el", "el": "el", "greek": "el",
        "heb": "he", "he": "he", "hebrew": "he",
        "cze": "cs", "ces": "cs", "cs": "cs", "czech": "cs",
        "hun": "hu", "hu": "hu", "hungarian": "hu",
        "rum": "ro", "ron": "ro", "ro": "ro", "romanian": "ro",
        "tha": "th", "th": "th", "thai": "th",
        "vie": "vi", "vi": "vi", "vietnamese": "vi",
    }

    # Upper bound for numbered subtitle file detection.
    MAX_SUBTITLE_TRACK_INDEX: int = 20

    def __init__(
        self,
        overwrite: bool = False,
        languages: Optional[List[str]] = None,
        dry_run: bool = False,
        threads: int = 1,
        include_forced: bool = False,
        include_sdh: bool = False,
        exclude_commentary: bool = False,
        track_title: Optional[str] = None,
        log_file: Optional[Path] = None,
        report_format: Optional[str] = None,
        convert_to: Optional[str] = None,
        output_dir: Optional[Path] = None,
        preserve_structure: bool = False,
        resume: bool = False,
        resume_file: Optional[Path] = None,
        retries: int = 0,
    ) -> None:
        self.overwrite = overwrite
        self.dry_run = dry_run
        self.threads = threads
        self.include_forced = include_forced
        self.include_sdh = include_sdh
        self.exclude_commentary = exclude_commentary
        self.track_title = track_title
        self.log_file = log_file
        self.report_format = report_format
        self.convert_to = convert_to
        self.output_dir = output_dir
        self.preserve_structure = preserve_structure
        self.resume = resume
        self.resume_file = resume_file or Path.home() / ".subtitle-extractor-resume.pkl"
        self.retries = max(0, retries)

        # Normalise and store target languages (default to English).
        self.target_languages: List[str] = self._normalize_languages(
            languages if languages is not None else ["en"]
        )

        self.stats: Dict[str, int] = {
            "processed": 0,
            "extracted": 0,
            "skipped": 0,
            "errors": 0,
        }

        self.total_files: int = 0
        self.current_file: int = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

        self.processed_files: Set[str] = set()
        if self.resume and self.resume_file.exists():
            self._load_resume_state()

        self.extraction_log: List[Dict] = []

        self._lock = threading.Lock()

        # Rich progress bar is disabled when logging to file (output clash).
        self.use_rich: bool = HAS_RICH and not log_file
        self.progress_bar: Optional[Progress] = None
        self.progress_task: Optional[object] = None

    # ------------------------------------------------------------------
    # Language helpers
    # ------------------------------------------------------------------

    def _normalize_languages(self, languages: List[str]) -> List[str]:
        """Return a sorted, deduplicated list of ISO 639-1 codes."""
        normalized: Set[str] = set()
        for lang in languages:
            lang_lower = lang.lower()
            normalized.add(self.LANGUAGE_CODES.get(lang_lower, lang_lower))
        return sorted(normalized)

    def _matches_language(self, lang_code: str) -> Tuple[bool, str]:
        """Return ``(matches, normalized_code)`` for *lang_code*."""
        if not lang_code:
            return False, ""
        lang_lower = lang_code.lower()
        normalized = self.LANGUAGE_CODES.get(lang_lower, lang_lower)
        return normalized in self.target_languages, normalized

    # ------------------------------------------------------------------
    # Track filtering
    # ------------------------------------------------------------------

    def _should_skip_track(self, track: Dict) -> Tuple[bool, str]:
        """Return ``(should_skip, reason)`` for a subtitle track dict."""
        track_name = track.get("track_name", "").lower()

        is_forced = track.get("forced", False) or "forced" in track_name
        if not self.include_forced and is_forced and not self.include_sdh:
            return True, "forced subtitle"

        is_sdh = "sdh" in track_name or "hearing impaired" in track_name or "cc" in track_name
        if not self.include_sdh and is_sdh:
            return True, "SDH/CC subtitle"

        is_commentary = "commentary" in track_name or "comment" in track_name
        if self.exclude_commentary and is_commentary:
            return True, "commentary track"

        if self.track_title and self.track_title.lower() not in track_name:
            return True, f"track title filter (looking for '{self.track_title}')"

        return False, ""

    # ------------------------------------------------------------------
    # Tool availability checks
    # ------------------------------------------------------------------

    @staticmethod
    def check_mkvtoolnix() -> bool:
        """Return True if mkvtoolnix (mkvmerge + mkvextract) is available."""
        try:
            subprocess.run(["mkvmerge", "--version"], capture_output=True, check=True)
            subprocess.run(["mkvextract", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def check_ffmpeg() -> bool:
        """Return True if ffmpeg and ffprobe are available."""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def check_pgsrip() -> bool:
        """Return True if pgsrip (OCR tool) is available."""
        try:
            subprocess.run(["pgsrip", "--help"], capture_output=True)
            return True
        except FileNotFoundError:
            return False

    # ------------------------------------------------------------------
    # Codec helpers
    # ------------------------------------------------------------------

    def _is_image_based_codec(self, codec: str) -> bool:
        """Return True when *codec* identifies an image-based subtitle format."""
        return codec.lower() in self.IMAGE_BASED_CODECS

    def get_extension_for_codec(self, codec: str) -> str:
        """Return the appropriate file extension for *codec*.

        Image-based codecs always map to their native format regardless of
        ``convert_to`` (OCR happens in a separate step).  For text codecs,
        ``convert_to`` takes precedence when set.
        """
        if self.convert_to and not self._is_image_based_codec(codec):
            return self.convert_to

        codec_lower = codec.lower()

        # Exact match first (avoids e.g. 'sub' hitting 'subtitle').
        if codec_lower in self.CODEC_EXTENSIONS:
            return self.CODEC_EXTENSIONS[codec_lower]

        # Substring fallback for compound codec strings like "SubRip/SRT".
        for name, ext in self.CODEC_EXTENSIONS.items():
            if name in codec_lower:
                return ext

        return "srt"

    # ------------------------------------------------------------------
    # Output path generation
    # ------------------------------------------------------------------

    def _get_output_path(
        self, video_file: Path, lang: str, extension: str, index: int = 0
    ) -> Path:
        """Return the destination path for an extracted subtitle file."""
        if index == 0:
            filename = f"{video_file.stem}.{lang}.{extension}"
        else:
            filename = f"{video_file.stem}.{lang}.{index}.{extension}"

        if self.output_dir:
            if self.preserve_structure and hasattr(self, "base_directory"):
                rel_path = video_file.parent.relative_to(self.base_directory)
                output_path = self.output_dir / rel_path / filename
            else:
                output_path = self.output_dir / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_path = video_file.parent / filename

        return output_path

    # ------------------------------------------------------------------
    # Resume state
    # ------------------------------------------------------------------

    def _load_resume_state(self) -> None:
        """Load previously processed file paths from the resume pickle."""
        try:
            with open(self.resume_file, "rb") as fh:
                self.processed_files = pickle.load(fh)
            logging.info(f"Resumed: {len(self.processed_files)} files already processed")
        except (FileNotFoundError, EOFError, pickle.UnpicklingError) as exc:
            logging.warning(f"Could not load resume state: {exc}")
            self.processed_files = set()

    def _save_resume_state(self) -> None:
        """Persist processed file paths to the resume pickle."""
        try:
            with open(self.resume_file, "wb") as fh:
                pickle.dump(self.processed_files, fh)
        except OSError as exc:
            logging.warning(f"Could not save resume state: {exc}")

    # ------------------------------------------------------------------
    # Progress bar
    # ------------------------------------------------------------------

    def _init_progress_bar(self) -> None:
        """Initialise the rich progress bar if available."""
        if not self.use_rich:
            return
        try:
            self.progress_bar = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TextColumn("•"),
                TimeRemainingColumn(),
            )
            self.progress_task = self.progress_bar.add_task(
                "Extracting subtitles", total=self.total_files
            )
        except Exception as exc:
            logging.debug(f"Failed to initialise progress bar: {exc}")
            self.use_rich = False

    def _print_progress(self) -> None:
        """Update or print progress information."""
        if self.use_rich and self.progress_bar and self.progress_task is not None:
            self.progress_bar.update(self.progress_task, completed=self.current_file)
        else:
            pct = (self.current_file / self.total_files * 100) if self.total_files else 0
            remaining = self.total_files - self.current_file
            logging.info(
                f"  Progress: {self.current_file}/{self.total_files} files "
                f"({pct:.1f}%) | {remaining} remaining"
            )

    # ------------------------------------------------------------------
    # Track discovery
    # ------------------------------------------------------------------

    def get_subtitle_tracks(self, mkv_file: Path) -> List[Dict]:
        """Return filtered subtitle tracks from an MKV file (via mkvmerge)."""
        try:
            result = subprocess.run(
                ["mkvmerge", "-J", str(mkv_file)],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as exc:
            logging.error(f"  Error reading tracks: {exc}")
            return []

        matching: List[Dict] = []
        for track in data.get("tracks", []):
            if track["type"] != "subtitles":
                continue
            props = track.get("properties", {})
            lang_code = props.get("language", "")
            matches, normalized = self._matches_language(lang_code)
            if not matches:
                continue
            track_info: Dict = {
                "id": track["id"],
                "codec": track["codec"],
                "track_name": props.get("track_name", ""),
                "language": normalized,
                "forced": props.get("forced_track", False),
            }
            should_skip, reason = self._should_skip_track(track_info)
            if not should_skip:
                matching.append(track_info)
            else:
                logging.debug(f"Skipping track {track['id']}: {reason}")
        return matching

    def get_subtitle_tracks_mp4(self, mp4_file: Path) -> List[Dict]:
        """Return filtered subtitle tracks from an MP4/ffmpeg file (via ffprobe)."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", str(mp4_file)],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as exc:
            logging.error(f"  Error reading tracks: {exc}")
            return []

        matching: List[Dict] = []
        for stream in data.get("streams", []):
            if stream.get("codec_type") != "subtitle":
                continue
            tags = stream.get("tags", {})
            lang_code = tags.get("language", tags.get("LANGUAGE", ""))
            matches, normalized = self._matches_language(lang_code)
            if not matches:
                continue
            disposition = stream.get("disposition", {})
            track_info: Dict = {
                "id": stream["index"],
                "codec": stream.get("codec_name", "unknown"),
                "track_name": tags.get("title", tags.get("TITLE", "")),
                "language": normalized,
                "forced": disposition.get("forced", 0) == 1,
            }
            should_skip, reason = self._should_skip_track(track_info)
            if not should_skip:
                matching.append(track_info)
            else:
                logging.debug(f"Skipping stream {stream['index']}: {reason}")
        return matching

    def _get_all_subtitle_tracks_mkv(self, mkv_file: Path) -> List[Dict]:
        """Return ALL subtitle tracks from an MKV file (no language filtering)."""
        try:
            result = subprocess.run(
                ["mkvmerge", "-J", str(mkv_file)],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError, KeyError) as exc:
            logging.error(f"Error reading tracks: {exc}")
            return []

        tracks: List[Dict] = []
        for track in data.get("tracks", []):
            if track["type"] != "subtitles":
                continue
            props = track.get("properties", {})
            tracks.append({
                "id": track["id"],
                "codec": track["codec"],
                "language": props.get("language", "und"),
                "track_name": props.get("track_name", ""),
                "forced": props.get("forced_track", False),
            })
        return tracks

    def _get_all_subtitle_tracks_ffmpeg(self, video_file: Path) -> List[Dict]:
        """Return ALL subtitle tracks from an ffmpeg-supported file (no filtering)."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", str(video_file)],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError, KeyError) as exc:
            logging.error(f"Error reading tracks: {exc}")
            return []

        tracks: List[Dict] = []
        for stream in data.get("streams", []):
            if stream.get("codec_type") != "subtitle":
                continue
            tags = stream.get("tags", {})
            disposition = stream.get("disposition", {})
            tracks.append({
                "id": stream["index"],
                "codec": stream.get("codec_name", "unknown"),
                "language": tags.get("language", tags.get("LANGUAGE", "und")),
                "track_name": tags.get("title", tags.get("TITLE", "")),
                "forced": disposition.get("forced", 0) == 1,
            })
        return tracks

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract_subtitle(
        self, mkv_file: Path, track_id: int, output_file: Path
    ) -> bool:
        """Extract a single subtitle track from an MKV file, with retries."""
        for attempt in range(self.retries + 1):
            try:
                subprocess.run(
                    ["mkvextract", str(mkv_file), "tracks", f"{track_id}:{output_file}"],
                    capture_output=True, check=True,
                )
                return True
            except subprocess.CalledProcessError as exc:
                if attempt < self.retries:
                    wait = 0.5 * (attempt + 1)
                    logging.warning(
                        f"  Retry {attempt + 1}/{self.retries} for track {track_id} "
                        f"(waiting {wait:.1f}s): {exc}"
                    )
                    time.sleep(wait)
                else:
                    logging.error(f"  Error extracting track {track_id}: {exc}")
        return False

    def extract_subtitle_mp4(
        self, mp4_file: Path, track_id: int, output_file: Path
    ) -> bool:
        """Extract a single subtitle track from an MP4/ffmpeg file, with retries."""
        for attempt in range(self.retries + 1):
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "quiet", "-i", str(mp4_file),
                     "-map", f"0:{track_id}", "-c", "copy", str(output_file)],
                    capture_output=True, check=True,
                )
                return True
            except subprocess.CalledProcessError as exc:
                if attempt < self.retries:
                    wait = 0.5 * (attempt + 1)
                    logging.warning(
                        f"  Retry {attempt + 1}/{self.retries} for track {track_id} "
                        f"(waiting {wait:.1f}s): {exc}"
                    )
                    time.sleep(wait)
                else:
                    logging.error(f"  Error extracting track {track_id}: {exc}")
        return False

    # ------------------------------------------------------------------
    # Format conversion
    # ------------------------------------------------------------------

    def _convert_subtitle(
        self, input_file: Path, output_file: Path, source_codec: str = ""
    ) -> bool:
        """Convert *input_file* to ``convert_to`` format.

        Image-based codecs are routed through pgsrip (OCR); text codecs use ffmpeg.
        Returns True on success or when no conversion is needed.
        """
        if not self.convert_to or input_file.suffix.lstrip(".") == self.convert_to:
            return True

        is_image = self._is_image_based_codec(source_codec) or input_file.suffix in (".sup", ".sub")

        if is_image and self.convert_to == "srt":
            return self._ocr_convert(input_file, output_file)
        if is_image:
            logging.warning(
                f"Cannot convert image-based subtitle {input_file.name} to "
                f"{self.convert_to} — leaving as-is"
            )
            return True

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(input_file), str(output_file)],
                capture_output=True, check=True,
            )
            if output_file.exists() and input_file != output_file:
                input_file.unlink()
            return True
        except subprocess.CalledProcessError as exc:
            logging.error(f"Error converting {input_file} to {self.convert_to}: {exc}")
            return False

    def _ocr_convert(self, input_file: Path, output_file: Path) -> bool:
        """Convert an image-based subtitle to SRT via pgsrip OCR."""
        if not self.check_pgsrip():
            logging.error(
                "pgsrip is required to convert image-based subtitles to SRT.\n"
                "Install with: pip install pgsrip\n"
                "Also ensure Tesseract is installed: apt install tesseract-ocr"
            )
            return False

        try:
            result = subprocess.run(
                ["pgsrip", str(input_file)],
                capture_output=True, text=True, check=True,
            )
            pgsrip_output = input_file.with_suffix(".srt")
            if pgsrip_output.exists():
                if pgsrip_output != output_file:
                    pgsrip_output.rename(output_file)
                if input_file.exists() and input_file != output_file:
                    input_file.unlink()
                return True
            logging.error(
                f"pgsrip did not produce output for {input_file.name}: {result.stderr}"
            )
            return False
        except subprocess.CalledProcessError as exc:
            logging.error(f"pgsrip failed for {input_file.name}: {exc.stderr}")
            return False

    # ------------------------------------------------------------------
    # Existing subtitle detection
    # ------------------------------------------------------------------

    def _check_existing_subtitles(self, video_file: Path) -> bool:
        """Return True if a subtitle file already exists for at least one target language."""
        subtitle_extensions = [".srt", ".ass", ".sup", ".sub", ".ssa"]
        for lang in self.target_languages:
            for ext in subtitle_extensions:
                if (video_file.parent / f"{video_file.stem}.{lang}{ext}").exists():
                    return True
            for i in range(1, self.MAX_SUBTITLE_TRACK_INDEX + 1):
                for ext in subtitle_extensions:
                    if (video_file.parent / f"{video_file.stem}.{lang}.{i}{ext}").exists():
                        return True
        return False

    # ------------------------------------------------------------------
    # Single-file processing
    # ------------------------------------------------------------------

    def process_video_file(self, video_file: Path) -> Dict:
        """Process one video file; return a result dict for reporting."""
        file_key = str(video_file.absolute())

        if self.resume and file_key in self.processed_files:
            logging.info(f"Skipped (already processed): {video_file}")
            return {"file": str(video_file), "status": "resumed_skip", "subtitles": []}

        if not self.overwrite and not self.dry_run:
            if self._check_existing_subtitles(video_file):
                if not self.use_rich:
                    logging.info(f"Processing: {video_file}")
                    logging.info("  Skipped: subtitle files already exist (use --overwrite to force)")
                with self._lock:
                    self.stats["skipped"] += 1
                return {"file": str(video_file), "status": "subtitles_exist", "subtitles": []}

        if not self.use_rich:
            logging.info(f"Processing: {video_file}")
        with self._lock:
            self.stats["processed"] += 1

        result: Dict = {"file": str(video_file), "status": "processed", "subtitles": [], "errors": []}

        file_ext = video_file.suffix.lower()
        if file_ext == ".mkv":
            subtitle_tracks = self.get_subtitle_tracks(video_file)
            extract_method = self.extract_subtitle
        elif file_ext in self.FFMPEG_FORMATS:
            subtitle_tracks = self.get_subtitle_tracks_mp4(video_file)
            extract_method = self.extract_subtitle_mp4
        else:
            logging.info(f"  Skipped: unsupported file format ({file_ext})")
            with self._lock:
                self.stats["skipped"] += 1
            result["status"] = "unsupported"
            return result

        if not subtitle_tracks:
            lang_list = ", ".join(self.target_languages)
            logging.info(f"  Skipped: no subtitles found for language(s): {lang_list}")
            with self._lock:
                self.stats["skipped"] += 1
            result["status"] = "no_subtitles"
            return result

        # Group tracks by language for consistent naming.
        tracks_by_lang: Dict[str, List[Dict]] = {}
        for track in subtitle_tracks:
            tracks_by_lang.setdefault(track["language"], []).append(track)

        extracted_count = 0
        for lang, lang_tracks in sorted(tracks_by_lang.items()):
            for idx, track in enumerate(lang_tracks):
                extension = self.get_extension_for_codec(track["codec"])
                output_file = self._get_output_path(
                    video_file, lang, extension,
                    idx + 1 if len(lang_tracks) > 1 else 0,
                )

                if output_file.exists() and not self.overwrite:
                    logging.info(f"  Skipped: {output_file.name} already exists")
                    with self._lock:
                        self.stats["skipped"] += 1
                    continue

                if self.dry_run:
                    suffix = f" ({track['track_name']})" if track["track_name"] else ""
                    logging.info(f"  [DRY-RUN] Would extract: {output_file.name}{suffix}")
                    result["subtitles"].append(
                        {"output": str(output_file), "language": lang, "dry_run": True}
                    )
                    extracted_count += 1
                    continue

                if extract_method(video_file, track["id"], output_file):
                    if self.convert_to:
                        final_output = output_file.with_suffix(f".{self.convert_to}")
                        if not self._convert_subtitle(output_file, final_output, track["codec"]):
                            with self._lock:
                                self.stats["errors"] += 1
                            result["errors"].append(f"Conversion failed for {output_file.name}")
                            continue
                        output_file = final_output

                    suffix = f" ({track['track_name']})" if track["track_name"] else ""
                    logging.info(f"  Extracted: {output_file.name}{suffix}")
                    result["subtitles"].append({"output": str(output_file), "language": lang})
                    extracted_count += 1
                    with self._lock:
                        self.stats["extracted"] += 1
                else:
                    with self._lock:
                        self.stats["errors"] += 1
                    result["errors"].append(f"Extraction failed for track {track['id']}")

        if extracted_count == 0 and subtitle_tracks and not self.dry_run:
            logging.info("  No new subtitles extracted")

        if not self.dry_run:
            with self._lock:
                self.processed_files.add(file_key)

        return result

    # ------------------------------------------------------------------
    # Track inspection mode
    # ------------------------------------------------------------------

    def list_tracks_in_file(self, video_file: Path) -> Dict:
        """Return a dict describing all subtitle tracks in *video_file*."""
        file_ext = video_file.suffix.lower()
        if file_ext == ".mkv":
            all_tracks = self._get_all_subtitle_tracks_mkv(video_file)
        elif file_ext in self.FFMPEG_FORMATS:
            all_tracks = self._get_all_subtitle_tracks_ffmpeg(video_file)
        else:
            return {"file": str(video_file), "error": "Unsupported format"}

        evaluated: List[Dict] = []
        for track in all_tracks:
            matches, normalized = self._matches_language(track.get("language", ""))
            should_skip, reason = (
                self._should_skip_track(track) if matches else (True, "language")
            )
            evaluated.append({
                **track,
                "would_extract": matches and not should_skip,
                "skip_reason": reason if matches else "language mismatch",
                "normalized_language": normalized if matches else track.get("language", "und"),
            })

        return {"file": str(video_file), "tracks": evaluated}

    def display_track_list(self, track_info: Dict) -> None:
        """Print a formatted table of tracks in *track_info*."""
        print(f"\n{'=' * 80}")
        print(f"File: {track_info['file']}")
        print(f"{'=' * 80}")

        if "error" in track_info:
            print(f"Error: {track_info['error']}")
            return

        tracks = track_info.get("tracks", [])
        if not tracks:
            print("No subtitle tracks found")
            return

        if HAS_RICH:
            try:
                from rich.console import Console
                from rich.table import Table

                console = Console()
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("ID", style="cyan", width=6)
                table.add_column("Language", style="green", width=10)
                table.add_column("Codec", style="yellow", width=15)
                table.add_column("Forced", width=8)
                table.add_column("Track Name", width=25)
                table.add_column("Will Extract?", width=15)

                for track in tracks:
                    will_extract = (
                        "✓ Yes" if track["would_extract"]
                        else f"✗ No ({track['skip_reason']})"
                    )
                    name = track.get("track_name", "-")
                    if len(name) > 25:
                        name = name[:22] + "..."
                    table.add_row(
                        str(track["id"]),
                        track.get("normalized_language", track.get("language", "und")),
                        track["codec"],
                        "Yes" if track.get("forced", False) else "No",
                        name,
                        will_extract,
                    )
                console.print(table)
                return
            except Exception:
                pass

        # Fallback plain-text table.
        print(f"{'ID':<6} {'Lang':<10} {'Codec':<15} {'Forced':<8} {'Track Name':<25} {'Extract?':<15}")
        print("-" * 80)
        for track in tracks:
            will_extract = "Yes" if track["would_extract"] else f"No ({track['skip_reason']})"
            name = track.get("track_name", "-")
            if len(name) > 25:
                name = name[:22] + "..."
            print(
                f"{track['id']:<6} "
                f"{track.get('normalized_language', track.get('language', 'und')):<10} "
                f"{track['codec']:<15} "
                f"{'Yes' if track.get('forced', False) else 'No':<8} "
                f"{name:<25} "
                f"{will_extract:<15}"
            )

    # ------------------------------------------------------------------
    # Directory processing
    # ------------------------------------------------------------------

    def process_directory(self, directory: Path) -> None:
        """Recursively find and process all video files under *directory*."""
        mkv_files = sorted(directory.rglob("*.mkv"))
        ffmpeg_files: List[Path] = []
        for ext in ("*.mp4", "*.webm", "*.mov", "*.avi"):
            ffmpeg_files.extend(directory.rglob(ext))
        ffmpeg_files = sorted(ffmpeg_files)
        video_files = sorted(mkv_files + ffmpeg_files)

        # Sidecar .sup files for OCR when convert_to='srt'.
        sidecar_sups: List[Path] = []
        if self.convert_to == "srt":
            for sup_file in sorted(directory.rglob("*.sup")):
                if not sup_file.with_suffix(".srt").exists() or self.overwrite:
                    sidecar_sups.append(sup_file)

        if not video_files:
            logging.info(f"No video files found in {directory}")
            return

        self.base_directory = directory
        self.total_files = len(video_files)
        logging.info(
            f"Found {len(video_files)} total file(s) "
            f"(MKV: {len(mkv_files)}, Other: {len(ffmpeg_files)})\n"
        )
        if sidecar_sups:
            logging.info(f"Found {len(sidecar_sups)} sidecar .sup file(s) to OCR\n")
        if self.dry_run:
            logging.info("[DRY-RUN MODE] No files will be modified\n")

        self.start_time = datetime.now()
        logging.info(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        self._init_progress_bar()

        if self.use_rich and self.progress_bar:
            with self.progress_bar:
                if self.threads > 1:
                    self._process_parallel(video_files)
                else:
                    self._process_sequential(video_files)
        else:
            if self.threads > 1:
                self._process_parallel(video_files)
            else:
                self._process_sequential(video_files)

        if sidecar_sups and not self.dry_run:
            logging.info("\nProcessing sidecar .sup files with OCR...")
            for sup_file in sidecar_sups:
                logging.info(f"  OCR: {sup_file.name}")
                srt_output = sup_file.with_suffix(".srt")
                if self._ocr_convert(sup_file, srt_output):
                    logging.info(f"    -> {srt_output.name}")
                    self.stats["extracted"] += 1
                else:
                    self.stats["errors"] += 1
        elif sidecar_sups and self.dry_run:
            logging.info(f"\n[DRY-RUN] Would OCR {len(sidecar_sups)} sidecar .sup file(s)")

        self.end_time = datetime.now()

        if not self.dry_run:
            self._save_resume_state()
            self._save_reports()

    def _process_sequential(self, video_files: List[Path]) -> None:
        """Process video files one at a time."""
        for video_file in video_files:
            try:
                self.current_file += 1
                result = self.process_video_file(video_file)
                self.extraction_log.append(result)
                self._print_progress()
                if not self.use_rich:
                    logging.info("")
            except (subprocess.SubprocessError, OSError, ValueError) as exc:
                logging.error(f"Unexpected error processing {video_file}: {exc}")
                self.stats["errors"] += 1
                self._print_progress()
                if not self.use_rich:
                    logging.info("")

    def _process_parallel(self, video_files: List[Path]) -> None:
        """Process video files in parallel via a thread pool."""
        logging.info(f"Using {self.threads} threads for parallel processing\n")
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            future_to_file = {executor.submit(self.process_video_file, f): f for f in video_files}
            for future in as_completed(future_to_file):
                video_file = future_to_file[future]
                try:
                    result = future.result()
                    with self._lock:
                        self.current_file += 1
                        self.extraction_log.append(result)
                    self._print_progress()
                    if not self.use_rich:
                        logging.info("")
                except (subprocess.SubprocessError, OSError, ValueError) as exc:
                    logging.error(f"Unexpected error processing {video_file}: {exc}")
                    with self._lock:
                        self.stats["errors"] += 1
                    if not self.use_rich:
                        logging.info("")

    # ------------------------------------------------------------------
    # Reports & summary
    # ------------------------------------------------------------------

    def _save_reports(self) -> None:
        """Write JSON or CSV extraction report if requested."""
        if not self.report_format or not self.extraction_log:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.report_format == "json":
            report_file = Path(f"subtitle_extraction_{timestamp}.json")
            with open(report_file, "w") as fh:
                json.dump(
                    {"timestamp": timestamp, "stats": self.stats, "files": self.extraction_log},
                    fh, indent=2,
                )
            logging.info(f"\nReport saved to: {report_file}")

        elif self.report_format == "csv":
            report_file = Path(f"subtitle_extraction_{timestamp}.csv")
            with open(report_file, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["File", "Status", "Subtitles Extracted", "Errors"])
                for entry in self.extraction_log:
                    writer.writerow([
                        entry["file"],
                        entry["status"],
                        len(entry.get("subtitles", [])),
                        "; ".join(entry.get("errors", [])),
                    ])
            logging.info(f"\nReport saved to: {report_file}")

    def print_summary(self) -> None:
        """Print a human-readable extraction summary."""
        logging.info("=" * 50)
        logging.info("SUMMARY")
        logging.info("=" * 50)
        logging.info(f"Files processed:      {self.stats['processed']}")
        logging.info(f"Subtitles extracted:  {self.stats['extracted']}")
        logging.info(f"Files skipped:        {self.stats['skipped']}")
        logging.info(f"Errors encountered:   {self.stats['errors']}")

        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            hours, rem = divmod(int(duration.total_seconds()), 3600)
            minutes, seconds = divmod(rem, 60)
            logging.info("")
            logging.info(f"Started:              {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"Finished:             {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if hours > 0:
                logging.info(f"Duration:             {hours}h {minutes}m {seconds}s")
            elif minutes > 0:
                logging.info(f"Duration:             {minutes}m {seconds}s")
            else:
                logging.info(f"Duration:             {seconds}s")
