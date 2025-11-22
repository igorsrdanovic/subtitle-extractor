#!/usr/bin/env python3
"""
MKV/MP4 Subtitle Extractor
Extracts subtitles from MKV and MP4 files recursively with advanced features.
"""

import argparse
import csv
import json
import logging
import pickle
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class SubtitleExtractor:
    """Handles extraction of English subtitles from MKV and MP4 files."""

    # Codec to extension mapping
    CODEC_EXTENSIONS = {
        'SubRip/SRT': 'srt',
        'subrip': 'srt',
        'srt': 'srt',
        'SubStationAlpha': 'ass',
        'ASS': 'ass',
        'SSA': 'ass',
        'ass': 'ass',
        'ssa': 'ass',
        'HDMV PGS': 'sup',
        'VobSub': 'sup',
        'hdmv_pgs_subtitle': 'sup',
        'dvd_subtitle': 'sup',
        'mov_text': 'srt',  # MP4 text subtitles
        'tx3g': 'srt',      # MP4 timed text
    }

    # Language code normalization mapping
    LANGUAGE_CODES = {
        'eng': 'en', 'en': 'en', 'english': 'en',
        'spa': 'es', 'es': 'es', 'spanish': 'es',
        'fre': 'fr', 'fra': 'fr', 'fr': 'fr', 'french': 'fr',
        'ger': 'de', 'deu': 'de', 'de': 'de', 'german': 'de',
        'ita': 'it', 'it': 'it', 'italian': 'it',
        'por': 'pt', 'pt': 'pt', 'portuguese': 'pt',
        'rus': 'ru', 'ru': 'ru', 'russian': 'ru',
        'jpn': 'ja', 'ja': 'ja', 'japanese': 'ja',
        'chi': 'zh', 'zho': 'zh', 'zh': 'zh', 'chinese': 'zh',
        'kor': 'ko', 'ko': 'ko', 'korean': 'ko',
        'ara': 'ar', 'ar': 'ar', 'arabic': 'ar',
        'hin': 'hi', 'hi': 'hi', 'hindi': 'hi',
        'dut': 'nl', 'nld': 'nl', 'nl': 'nl', 'dutch': 'nl',
        'pol': 'pl', 'pl': 'pl', 'polish': 'pl',
        'swe': 'sv', 'sv': 'sv', 'swedish': 'sv',
        'nor': 'no', 'no': 'no', 'norwegian': 'no',
        'dan': 'da', 'da': 'da', 'danish': 'da',
        'fin': 'fi', 'fi': 'fi', 'finnish': 'fi',
        'tur': 'tr', 'tr': 'tr', 'turkish': 'tr',
        'gre': 'el', 'ell': 'el', 'el': 'el', 'greek': 'el',
        'heb': 'he', 'he': 'he', 'hebrew': 'he',
        'cze': 'cs', 'ces': 'cs', 'cs': 'cs', 'czech': 'cs',
        'hun': 'hu', 'hu': 'hu', 'hungarian': 'hu',
        'rum': 'ro', 'ron': 'ro', 'ro': 'ro', 'romanian': 'ro',
        'tha': 'th', 'th': 'th', 'thai': 'th',
        'vie': 'vi', 'vi': 'vi', 'vietnamese': 'vi',
    }

    def __init__(self, overwrite: bool = False, languages: List[str] = None,
                 dry_run: bool = False, threads: int = 1,
                 include_forced: bool = False, include_sdh: bool = False,
                 exclude_commentary: bool = False, track_title: Optional[str] = None,
                 log_file: Optional[Path] = None, report_format: Optional[str] = None,
                 convert_to: Optional[str] = None, output_dir: Optional[Path] = None,
                 preserve_structure: bool = False, resume: bool = False,
                 resume_file: Optional[Path] = None):
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
        self.resume_file = resume_file or Path.home() / '.subtitle-extractor-resume.pkl'

        # Normalize and store target languages (default to English)
        if languages is None:
            languages = ['en']
        self.target_languages = self._normalize_languages(languages)

        self.stats = {
            'processed': 0,
            'extracted': 0,
            'skipped': 0,
            'errors': 0
        }

        # Progress tracking
        self.total_files = 0
        self.current_file = 0

        # Resume tracking - processed files
        self.processed_files: Set[str] = set()
        if self.resume and self.resume_file.exists():
            self._load_resume_state()

        # Report data
        self.extraction_log: List[Dict] = []

        # Setup logging
        self._setup_logging()

    def _normalize_languages(self, languages: List[str]) -> List[str]:
        """Normalize language codes to ISO 639-1 format."""
        normalized = set()
        for lang in languages:
            lang_lower = lang.lower()
            # Check if it's already a normalized code or can be normalized
            if lang_lower in self.LANGUAGE_CODES:
                normalized.add(self.LANGUAGE_CODES[lang_lower])
            else:
                # Keep the original if not in mapping (user-specified code)
                normalized.add(lang_lower)
        return sorted(list(normalized))

    def _matches_language(self, lang_code: str) -> Tuple[bool, str]:
        """Check if a language code matches any target language.
        Returns (matches, normalized_code)."""
        if not lang_code:
            return False, ''

        lang_lower = lang_code.lower()
        normalized = self.LANGUAGE_CODES.get(lang_lower, lang_lower)

        return normalized in self.target_languages, normalized

    def _setup_logging(self) -> None:
        """Setup logging configuration."""
        if self.log_file:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(self.log_file),
                    logging.StreamHandler()
                ]
            )
        else:
            logging.basicConfig(level=logging.INFO, format='%(message)s')

    def _load_resume_state(self) -> None:
        """Load processed files from resume file."""
        try:
            with open(self.resume_file, 'rb') as f:
                self.processed_files = pickle.load(f)
            logging.info(f"Resumed: {len(self.processed_files)} files already processed")
        except Exception as e:
            logging.warning(f"Could not load resume state: {e}")
            self.processed_files = set()

    def _save_resume_state(self) -> None:
        """Save processed files to resume file."""
        try:
            with open(self.resume_file, 'wb') as f:
                pickle.dump(self.processed_files, f)
        except Exception as e:
            logging.warning(f"Could not save resume state: {e}")

    def _should_skip_track(self, track: Dict) -> Tuple[bool, str]:
        """Check if track should be skipped based on filtering options.
        Returns (should_skip, reason)."""
        track_name = track.get('track_name', '').lower()

        # Check forced flag
        is_forced = track.get('forced', False) or 'forced' in track_name
        if not self.include_forced and is_forced and not self.include_sdh:
            return True, "forced subtitle"

        # Check SDH/hearing impaired
        is_sdh = 'sdh' in track_name or 'hearing impaired' in track_name or 'cc' in track_name
        if not self.include_sdh and is_sdh:
            return True, "SDH/CC subtitle"

        # Check commentary
        is_commentary = 'commentary' in track_name or 'comment' in track_name
        if self.exclude_commentary and is_commentary:
            return True, "commentary track"

        # Check track title filter
        if self.track_title and self.track_title.lower() not in track_name:
            return True, f"track title filter (looking for '{self.track_title}')"

        return False, ""

    @staticmethod
    def check_mkvtoolnix() -> bool:
        """Check if mkvtoolnix tools are installed."""
        try:
            subprocess.run(['mkvmerge', '--version'],
                         capture_output=True, check=True)
            subprocess.run(['mkvextract', '--version'],
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def check_ffmpeg() -> bool:
        """Check if ffmpeg and ffprobe are installed."""
        try:
            subprocess.run(['ffmpeg', '-version'],
                         capture_output=True, check=True)
            subprocess.run(['ffprobe', '-version'],
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def get_subtitle_tracks(self, mkv_file: Path) -> List[Dict]:
        """Extract information about subtitle tracks matching target languages from MKV file."""
        try:
            result = subprocess.run(
                ['mkvmerge', '-J', str(mkv_file)],
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)

            matching_subs = []
            for track in data.get('tracks', []):
                if track['type'] == 'subtitles':
                    lang_code = track.get('properties', {}).get('language', '')
                    matches, normalized = self._matches_language(lang_code)
                    if matches:
                        track_info = {
                            'id': track['id'],
                            'codec': track['codec'],
                            'track_name': track.get('properties', {}).get('track_name', ''),
                            'language': normalized,
                            'forced': track.get('properties', {}).get('forced_track', False)
                        }

                        # Apply filtering
                        should_skip, reason = self._should_skip_track(track_info)
                        if not should_skip:
                            matching_subs.append(track_info)
                        elif not self.dry_run:
                            logging.debug(f"Skipping track {track['id']}: {reason}")

            return matching_subs
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            print(f"  Error reading tracks: {e}")
            return []

    def get_subtitle_tracks_mp4(self, mp4_file: Path) -> List[Dict]:
        """Extract information about subtitle tracks matching target languages from MP4 file."""
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                 '-show_streams', str(mp4_file)],
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)

            matching_subs = []
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'subtitle':
                    # Check language from tags
                    tags = stream.get('tags', {})
                    lang_code = tags.get('language', tags.get('LANGUAGE', ''))

                    matches, normalized = self._matches_language(lang_code)
                    if matches:
                        disposition = stream.get('disposition', {})
                        track_info = {
                            'id': stream['index'],
                            'codec': stream.get('codec_name', 'unknown'),
                            'track_name': tags.get('title', tags.get('TITLE', '')),
                            'language': normalized,
                            'forced': disposition.get('forced', 0) == 1
                        }

                        # Apply filtering
                        should_skip, reason = self._should_skip_track(track_info)
                        if not should_skip:
                            matching_subs.append(track_info)
                        elif not self.dry_run:
                            logging.debug(f"Skipping stream {stream['index']}: {reason}")

            return matching_subs
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            print(f"  Error reading tracks: {e}")
            return []

    def get_extension_for_codec(self, codec: str) -> str:
        """Determine file extension based on subtitle codec."""
        # If conversion is requested, return that extension
        if self.convert_to:
            return self.convert_to

        for codec_name, ext in self.CODEC_EXTENSIONS.items():
            if codec_name.lower() in codec.lower():
                return ext
        # Default to .srt if codec is unknown
        return 'srt'

    def _get_output_path(self, video_file: Path, lang: str, extension: str, index: int = 0) -> Path:
        """Generate output path for subtitle file."""
        # Generate filename
        if index == 0:
            filename = f"{video_file.stem}.{lang}.{extension}"
        else:
            filename = f"{video_file.stem}.{lang}.{index}.{extension}"

        # Determine output directory
        if self.output_dir:
            if self.preserve_structure:
                # Preserve directory structure relative to initial scan directory
                # This will be set later in process_directory
                rel_path = video_file.parent.relative_to(self.base_directory) if hasattr(self, 'base_directory') else Path()
                output_path = self.output_dir / rel_path / filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                # Flat structure in output directory
                output_path = self.output_dir / filename
                self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Same directory as video file
            output_path = video_file.parent / filename

        return output_path

    def _convert_subtitle(self, input_file: Path, output_file: Path) -> bool:
        """Convert subtitle format if needed."""
        if not self.convert_to or input_file.suffix[1:] == self.convert_to:
            return True  # No conversion needed

        try:
            # Use ffmpeg to convert subtitle format
            subprocess.run(
                ['ffmpeg', '-y', '-i', str(input_file), str(output_file)],
                capture_output=True,
                check=True
            )
            # Remove original if conversion successful
            if output_file.exists() and input_file != output_file:
                input_file.unlink()
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Error converting {input_file} to {self.convert_to}: {e}")
            return False

    def extract_subtitle(self, mkv_file: Path, track_id: int,
                        output_file: Path) -> bool:
        """Extract a single subtitle track from MKV file."""
        try:
            subprocess.run(
                ['mkvextract', str(mkv_file), 'tracks',
                 f'{track_id}:{output_file}'],
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"  Error extracting track {track_id}: {e}")
            return False

    def extract_subtitle_mp4(self, mp4_file: Path, track_id: int,
                            output_file: Path) -> bool:
        """Extract a single subtitle track from MP4 file."""
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-v', 'quiet', '-i', str(mp4_file),
                 '-map', f'0:{track_id}', '-c', 'copy', str(output_file)],
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"  Error extracting track {track_id}: {e}")
            return False

    def process_video_file(self, video_file: Path) -> Dict:
        """Process a single video file and extract subtitles.
        Returns dict with processing results for logging."""
        file_key = str(video_file.absolute())

        # Skip if already processed (resume mode)
        if self.resume and file_key in self.processed_files:
            print(f"Skipped (already processed): {video_file}")
            return {'file': str(video_file), 'status': 'resumed_skip', 'subtitles': []}

        print(f"Processing: {video_file}")
        self.stats['processed'] += 1

        result = {'file': str(video_file), 'status': 'processed', 'subtitles': [], 'errors': []}

        # Determine file type and get subtitle tracks
        file_extension = video_file.suffix.lower()
        if file_extension == '.mkv':
            subtitle_tracks = self.get_subtitle_tracks(video_file)
            extract_method = self.extract_subtitle
        elif file_extension == '.mp4':
            subtitle_tracks = self.get_subtitle_tracks_mp4(video_file)
            extract_method = self.extract_subtitle_mp4
        else:
            print(f"  Skipped: Unsupported file format")
            self.stats['skipped'] += 1
            result['status'] = 'unsupported'
            return result

        if not subtitle_tracks:
            lang_list = ', '.join(self.target_languages)
            print(f"  Skipped: No subtitles found for language(s): {lang_list}")
            self.stats['skipped'] += 1
            result['status'] = 'no_subtitles'
            return result

        # Group tracks by language for better naming
        tracks_by_lang = {}
        for track in subtitle_tracks:
            lang = track['language']
            if lang not in tracks_by_lang:
                tracks_by_lang[lang] = []
            tracks_by_lang[lang].append(track)

        # Extract each subtitle track
        extracted_count = 0
        for lang, lang_tracks in sorted(tracks_by_lang.items()):
            for idx, track in enumerate(lang_tracks):
                # Determine extension based on codec
                extension = self.get_extension_for_codec(track['codec'])

                # Generate output filename - use new method
                output_file = self._get_output_path(video_file, lang, extension,
                                                    idx + 1 if len(lang_tracks) > 1 else 0)

                # Check if file already exists
                if output_file.exists() and not self.overwrite:
                    print(f"  Skipped: {output_file.name} already exists")
                    self.stats['skipped'] += 1
                    continue

                # Dry-run mode - just show what would be extracted
                if self.dry_run:
                    track_info = f" ({track['track_name']})" if track['track_name'] else ""
                    print(f"  [DRY-RUN] Would extract: {output_file.name}{track_info}")
                    result['subtitles'].append({'output': str(output_file), 'language': lang, 'dry_run': True})
                    extracted_count += 1
                    continue

                # Extract the subtitle
                if extract_method(video_file, track['id'], output_file):
                    # Handle conversion if needed
                    if self.convert_to:
                        final_output = output_file.with_suffix(f'.{self.convert_to}')
                        if not self._convert_subtitle(output_file, final_output):
                            self.stats['errors'] += 1
                            result['errors'].append(f"Conversion failed for {output_file.name}")
                            continue
                        output_file = final_output

                    track_info = f" ({track['track_name']})" if track['track_name'] else ""
                    print(f"  Extracted: {output_file.name}{track_info}")
                    result['subtitles'].append({'output': str(output_file), 'language': lang})
                    extracted_count += 1
                    self.stats['extracted'] += 1
                else:
                    self.stats['errors'] += 1
                    result['errors'].append(f"Extraction failed for track {track['id']}")

        if extracted_count == 0 and subtitle_tracks and not self.dry_run:
            print(f"  No new subtitles extracted")

        # Mark as processed for resume functionality
        if not self.dry_run:
            self.processed_files.add(file_key)

        return result

    def _print_progress(self) -> None:
        """Print progress information."""
        remaining = self.total_files - self.current_file
        percentage = (self.current_file / self.total_files * 100) if self.total_files > 0 else 0
        print(f"  Progress: {self.current_file}/{self.total_files} files completed ({percentage:.1f}%) | {remaining} remaining")

    def process_directory(self, directory: Path) -> None:
        """Recursively process all MKV and MP4 files in directory."""
        mkv_files = sorted(directory.rglob('*.mkv'))
        mp4_files = sorted(directory.rglob('*.mp4'))
        video_files = sorted(mkv_files + mp4_files)

        if not video_files:
            print(f"No MKV or MP4 files found in {directory}")
            return

        # Set base directory for preserve_structure feature
        self.base_directory = directory

        # Set total files for progress tracking
        self.total_files = len(video_files)
        mkv_count = len(mkv_files)
        mp4_count = len(mp4_files)
        print(f"Found {mkv_count} MKV file(s) and {mp4_count} MP4 file(s)\n")

        if self.dry_run:
            print("[DRY-RUN MODE] No files will be modified\n")

        # Process files - parallel or sequential
        if self.threads > 1 and not self.dry_run:
            self._process_parallel(video_files)
        else:
            self._process_sequential(video_files)

        # Save resume state and reports
        if not self.dry_run:
            self._save_resume_state()
            self._save_reports()

    def _process_sequential(self, video_files: List[Path]) -> None:
        """Process video files sequentially."""
        for video_file in video_files:
            try:
                self.current_file += 1
                result = self.process_video_file(video_file)
                self.extraction_log.append(result)
                self._print_progress()
                print()  # Empty line between files
            except Exception as e:
                logging.error(f"Unexpected error processing {video_file}: {e}")
                self.stats['errors'] += 1
                self._print_progress()
                print()

    def _process_parallel(self, video_files: List[Path]) -> None:
        """Process video files in parallel using thread pool."""
        print(f"Using {self.threads} threads for parallel processing\n")

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            # Submit all tasks
            future_to_file = {executor.submit(self.process_video_file, f): f for f in video_files}

            # Process completed tasks
            for future in as_completed(future_to_file):
                video_file = future_to_file[future]
                try:
                    self.current_file += 1
                    result = future.result()
                    self.extraction_log.append(result)
                    self._print_progress()
                    print()
                except Exception as e:
                    logging.error(f"Unexpected error processing {video_file}: {e}")
                    self.stats['errors'] += 1
                    print()

    def _save_reports(self) -> None:
        """Save extraction reports if requested."""
        if not self.report_format or not self.extraction_log:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.report_format == 'json':
            report_file = Path(f"subtitle_extraction_{timestamp}.json")
            with open(report_file, 'w') as f:
                json.dump({
                    'timestamp': timestamp,
                    'stats': self.stats,
                    'files': self.extraction_log
                }, f, indent=2)
            print(f"\nReport saved to: {report_file}")

        elif self.report_format == 'csv':
            report_file = Path(f"subtitle_extraction_{timestamp}.csv")
            with open(report_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['File', 'Status', 'Subtitles Extracted', 'Errors'])
                for entry in self.extraction_log:
                    writer.writerow([
                        entry['file'],
                        entry['status'],
                        len(entry.get('subtitles', [])),
                        '; '.join(entry.get('errors', []))
                    ])
            print(f"\nReport saved to: {report_file}")

    def print_summary(self) -> None:
        """Print extraction summary."""
        print("=" * 50)
        print("SUMMARY")
        print("=" * 50)
        print(f"Files processed:      {self.stats['processed']}")
        print(f"Subtitles extracted:  {self.stats['extracted']}")
        print(f"Files skipped:        {self.stats['skipped']}")
        print(f"Errors encountered:   {self.stats['errors']}")


def load_config() -> Dict:
    """Load configuration from file if it exists."""
    config_locations = [
        Path.home() / '.subtitle-extractor.yaml',
        Path('.subtitle-extractor.yaml'),
    ]

    for config_file in config_locations:
        if config_file.exists():
            if HAS_YAML:
                try:
                    with open(config_file) as f:
                        config = yaml.safe_load(f)
                        print(f"Loaded configuration from: {config_file}\n")
                        return config or {}
                except Exception as e:
                    print(f"Warning: Could not load config from {config_file}: {e}")
            else:
                print(f"Warning: YAML library not installed. Install with: pip install pyyaml")
            break

    return {}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Extract subtitles from MKV and MP4 files with advanced features',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/tv/shows
  %(prog)s /path/to/movies --languages en es fr
  %(prog)s /path/to/videos --dry-run
  %(prog)s /path/to/videos --threads 4 --output-dir /path/to/subs
  %(prog)s /path/to/videos --convert-to srt --resume

Config file: Create ~/.subtitle-extractor.yaml with default settings
        """
    )
    parser.add_argument(
        'directory',
        type=Path,
        help='Directory containing video files (will search recursively)'
    )
    parser.add_argument(
        '-l', '--languages',
        nargs='+',
        help='Language codes to extract (default: en from config or en)'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing subtitle files'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be extracted without making changes'
    )
    parser.add_argument(
        '--threads',
        type=int,
        default=1,
        help='Number of parallel threads (default: 1)'
    )
    parser.add_argument(
        '--include-forced',
        action='store_true',
        help='Include forced subtitles'
    )
    parser.add_argument(
        '--include-sdh',
        action='store_true',
        help='Include SDH/hearing impaired subtitles'
    )
    parser.add_argument(
        '--exclude-commentary',
        action='store_true',
        help='Exclude commentary tracks'
    )
    parser.add_argument(
        '--track-title',
        help='Filter by track title (case-insensitive substring match)'
    )
    parser.add_argument(
        '--log-file',
        type=Path,
        help='Save log to file'
    )
    parser.add_argument(
        '--report-format',
        choices=['json', 'csv'],
        help='Generate extraction report in specified format'
    )
    parser.add_argument(
        '--convert-to',
        choices=['srt', 'ass'],
        help='Convert all subtitles to specified format'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Extract subtitles to specified directory'
    )
    parser.add_argument(
        '--preserve-structure',
        action='store_true',
        help='Preserve directory structure in output directory'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from previous run (skip already processed files)'
    )

    # Load config file
    config = load_config()

    args = parser.parse_args()

    # Merge config with args (args take precedence)
    languages = args.languages or config.get('languages', ['en'])
    overwrite = args.overwrite or config.get('overwrite', False)
    dry_run = args.dry_run or config.get('dry_run', False)
    threads = args.threads if args.threads > 1 else config.get('threads', 1)
    output_dir = args.output_dir or (Path(config['output_dir']) if 'output_dir' in config else None)
    preserve_structure = args.preserve_structure or config.get('preserve_structure', False)
    convert_to = args.convert_to or config.get('convert_to')

    # Validate directory
    if not args.directory.exists():
        print(f"Error: Directory does not exist: {args.directory}", file=sys.stderr)
        sys.exit(1)

    if not args.directory.is_dir():
        print(f"Error: Not a directory: {args.directory}", file=sys.stderr)
        sys.exit(1)

    # Check for required tools
    has_mkvtoolnix = SubtitleExtractor.check_mkvtoolnix()
    has_ffmpeg = SubtitleExtractor.check_ffmpeg()

    if not has_mkvtoolnix and not has_ffmpeg:
        print("Error: Neither mkvtoolnix nor ffmpeg is installed", file=sys.stderr)
        print("\nAt least one of these tools is required:", file=sys.stderr)
        print("\nFor MKV support, install mkvtoolnix:", file=sys.stderr)
        print("  Ubuntu/Debian: sudo apt-get install mkvtoolnix", file=sys.stderr)
        print("  Fedora/RHEL:   sudo dnf install mkvtoolnix", file=sys.stderr)
        print("  macOS:         brew install mkvtoolnix", file=sys.stderr)
        print("  Windows:       Download from https://mkvtoolnix.download/", file=sys.stderr)
        print("\nFor MP4 support, install ffmpeg:", file=sys.stderr)
        print("  Ubuntu/Debian: sudo apt-get install ffmpeg", file=sys.stderr)
        print("  Fedora/RHEL:   sudo dnf install ffmpeg", file=sys.stderr)
        print("  macOS:         brew install ffmpeg", file=sys.stderr)
        print("  Windows:       Download from https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)

    if not has_mkvtoolnix:
        print("Warning: mkvtoolnix not found. MKV files will be skipped.", file=sys.stderr)
        print("Install with: sudo apt-get install mkvtoolnix (Ubuntu/Debian)\n", file=sys.stderr)

    if not has_ffmpeg:
        print("Warning: ffmpeg not found. MP4 files will be skipped.", file=sys.stderr)
        print("Install with: sudo apt-get install ffmpeg (Ubuntu/Debian)\n", file=sys.stderr)

    # Process files
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
        resume=args.resume
    )

    # Show which languages we're extracting
    print(f"Extracting subtitles for: {', '.join(extractor.target_languages)}\n")

    extractor.process_directory(args.directory)
    extractor.print_summary()


if __name__ == '__main__':
    main()
