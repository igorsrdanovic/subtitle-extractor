#!/usr/bin/env python3
"""
MKV Subtitle Extractor
Extracts English subtitles from MKV files recursively.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional


class SubtitleExtractor:
    """Handles extraction of English subtitles from MKV files."""

    # Codec to extension mapping
    CODEC_EXTENSIONS = {
        'SubRip/SRT': 'srt',
        'SubStationAlpha': 'ass',
        'ASS': 'ass',
        'SSA': 'ass',
        'HDMV PGS': 'sup',
        'VobSub': 'sup',
    }

    def __init__(self, overwrite: bool = False):
        self.overwrite = overwrite
        self.stats = {
            'processed': 0,
            'extracted': 0,
            'skipped': 0,
            'errors': 0
        }

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

    def get_subtitle_tracks(self, mkv_file: Path) -> List[Dict]:
        """Extract information about English subtitle tracks from MKV file."""
        try:
            result = subprocess.run(
                ['mkvmerge', '-J', str(mkv_file)],
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)

            english_subs = []
            for track in data.get('tracks', []):
                if track['type'] == 'subtitles' and track.get('properties', {}).get('language') == 'eng':
                    english_subs.append({
                        'id': track['id'],
                        'codec': track['codec'],
                        'track_name': track.get('properties', {}).get('track_name', '')
                    })

            return english_subs
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
        """Extract a single subtitle track to a file."""
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

    def process_mkv_file(self, mkv_file: Path) -> None:
        """Process a single MKV file and extract English subtitles."""
        print(f"Processing: {mkv_file}")
        self.stats['processed'] += 1

        # Get English subtitle tracks
        subtitle_tracks = self.get_subtitle_tracks(mkv_file)

        if not subtitle_tracks:
            print(f"  Skipped: No English subtitles found")
            self.stats['skipped'] += 1
            return

        # Extract each English subtitle track
        extracted_count = 0
        for idx, track in enumerate(subtitle_tracks):
            # Determine extension based on codec
            extension = self.get_extension_for_codec(track['codec'])

            # Generate output filename
            if len(subtitle_tracks) == 1:
                output_file = mkv_file.parent / f"{mkv_file.stem}.en.{extension}"
            else:
                output_file = mkv_file.parent / f"{mkv_file.stem}.en.{idx + 1}.{extension}"

            # Check if file already exists
            if output_file.exists() and not self.overwrite:
                print(f"  Skipped: {output_file.name} already exists")
                self.stats['skipped'] += 1
                continue

            # Extract the subtitle
            if self.extract_subtitle(mkv_file, track['id'], output_file):
                track_info = f" ({track['track_name']})" if track['track_name'] else ""
                print(f"  Extracted: {output_file.name}{track_info}")
                extracted_count += 1
                self.stats['extracted'] += 1
            else:
                self.stats['errors'] += 1

        if extracted_count == 0 and subtitle_tracks:
            print(f"  No new subtitles extracted")

    def process_directory(self, directory: Path) -> None:
        """Recursively process all MKV files in directory."""
        mkv_files = sorted(directory.rglob('*.mkv'))

        if not mkv_files:
            print(f"No MKV files found in {directory}")
            return

        print(f"Found {len(mkv_files)} MKV file(s)\n")

        for mkv_file in mkv_files:
            try:
                self.process_mkv_file(mkv_file)
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
        description='Extract English subtitles from MKV files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/tv/shows
  %(prog)s /path/to/movies --overwrite
        """
    )
    parser.add_argument(
        'directory',
        type=Path,
        help='Directory containing MKV files (will search recursively)'
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

    # Check for mkvtoolnix
    if not SubtitleExtractor.check_mkvtoolnix():
        print("Error: mkvtoolnix is not installed", file=sys.stderr)
        print("\nInstallation instructions:", file=sys.stderr)
        print("  Ubuntu/Debian: sudo apt-get install mkvtoolnix", file=sys.stderr)
        print("  Fedora/RHEL:   sudo dnf install mkvtoolnix", file=sys.stderr)
        print("  macOS:         brew install mkvtoolnix", file=sys.stderr)
        print("  Windows:       Download from https://mkvtoolnix.download/", file=sys.stderr)
        sys.exit(1)

    # Process files
    extractor = SubtitleExtractor(overwrite=args.overwrite)
    extractor.process_directory(args.directory)
    extractor.print_summary()


if __name__ == '__main__':
    main()
