#!/usr/bin/env python3
"""
MKV/MP4 Subtitle Extractor
Extracts English subtitles from MKV and MP4 files recursively.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional


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

    def __init__(self, overwrite: bool = False, languages: List[str] = None):
        self.overwrite = overwrite
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
                        matching_subs.append({
                            'id': track['id'],
                            'codec': track['codec'],
                            'track_name': track.get('properties', {}).get('track_name', ''),
                            'language': normalized
                        })

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
                        matching_subs.append({
                            'id': stream['index'],
                            'codec': stream.get('codec_name', 'unknown'),
                            'track_name': tags.get('title', tags.get('TITLE', '')),
                            'language': normalized
                        })

            return matching_subs
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            print(f"  Error reading tracks: {e}")
            return []

    def get_extension_for_codec(self, codec: str) -> str:
        """Determine file extension based on subtitle codec."""
        for codec_name, ext in self.CODEC_EXTENSIONS.items():
            if codec_name.lower() in codec.lower():
                return ext
        # Default to .srt if codec is unknown
        return 'srt'

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

    def process_video_file(self, video_file: Path) -> None:
        """Process a single video file and extract English subtitles."""
        print(f"Processing: {video_file}")
        self.stats['processed'] += 1

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
            return

        if not subtitle_tracks:
            lang_list = ', '.join(self.target_languages)
            print(f"  Skipped: No subtitles found for language(s): {lang_list}")
            self.stats['skipped'] += 1
            return

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

                # Generate output filename with language code
                if len(lang_tracks) == 1:
                    output_file = video_file.parent / f"{video_file.stem}.{lang}.{extension}"
                else:
                    output_file = video_file.parent / f"{video_file.stem}.{lang}.{idx + 1}.{extension}"

                # Check if file already exists
                if output_file.exists() and not self.overwrite:
                    print(f"  Skipped: {output_file.name} already exists")
                    self.stats['skipped'] += 1
                    continue

                # Extract the subtitle
                if extract_method(video_file, track['id'], output_file):
                    track_info = f" ({track['track_name']})" if track['track_name'] else ""
                    print(f"  Extracted: {output_file.name}{track_info}")
                    extracted_count += 1
                    self.stats['extracted'] += 1
                else:
                    self.stats['errors'] += 1

        if extracted_count == 0 and subtitle_tracks:
            print(f"  No new subtitles extracted")

    def process_directory(self, directory: Path) -> None:
        """Recursively process all MKV and MP4 files in directory."""
        mkv_files = sorted(directory.rglob('*.mkv'))
        mp4_files = sorted(directory.rglob('*.mp4'))
        video_files = sorted(mkv_files + mp4_files)

        if not video_files:
            print(f"No MKV or MP4 files found in {directory}")
            return

        mkv_count = len(mkv_files)
        mp4_count = len(mp4_files)
        print(f"Found {mkv_count} MKV file(s) and {mp4_count} MP4 file(s)\n")

        for video_file in video_files:
            try:
                self.process_video_file(video_file)
                print()  # Empty line between files
            except Exception as e:
                print(f"  Unexpected error: {e}")
                self.stats['errors'] += 1
                print()

    def print_summary(self) -> None:
        """Print extraction summary."""
        print("=" * 50)
        print("SUMMARY")
        print("=" * 50)
        print(f"Files processed:      {self.stats['processed']}")
        print(f"Subtitles extracted:  {self.stats['extracted']}")
        print(f"Files skipped:        {self.stats['skipped']}")
        print(f"Errors encountered:   {self.stats['errors']}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Extract subtitles from MKV and MP4 files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/tv/shows
  %(prog)s /path/to/movies --languages en es fr
  %(prog)s /path/to/videos --languages spa --overwrite

Supported language codes: en, es, fr, de, it, pt, ru, ja, zh, ko, ar, hi, nl, pl, sv, no, da, fi, tr, el, he, cs, hu, ro, th, vi
You can also use ISO 639-2 codes (eng, spa, fra, etc.) or language names (english, spanish, french, etc.)

Note: Requires mkvtoolnix (for MKV) and ffmpeg (for MP4)
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
        default=['en'],
        help='Language codes to extract (default: en). Accepts ISO 639-1 (en), ISO 639-2 (eng), or language names (english)'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing subtitle files'
    )

    args = parser.parse_args()

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
    extractor = SubtitleExtractor(overwrite=args.overwrite, languages=args.languages)

    # Show which languages we're extracting
    print(f"Extracting subtitles for: {', '.join(extractor.target_languages)}\n")

    extractor.process_directory(args.directory)
    extractor.print_summary()


if __name__ == '__main__':
    main()
