# MKV Subtitle Extractor

A Python script that recursively extracts English subtitles from MKV files and saves them in the same directory as the source files.

## Features

- Recursively processes all MKV files in a directory
- Extracts only English subtitle tracks (language code: `eng`)
- Automatically detects subtitle codec and uses appropriate extension:
  - SubRip/SRT → `.srt`
  - ASS/SSA → `.ass`
  - PGS/VobSub → `.sup`
- Skips files that already have extracted subtitles
- Handles multiple English subtitle tracks per file
- Provides detailed progress reporting and summary
- Robust error handling

## Requirements

- Python 3.6 or higher
- mkvtoolnix (`mkvmerge` and `mkvextract`)

### Installing mkvtoolnix

**Ubuntu/Debian:**
```bash
sudo apt-get install mkvtoolnix
```

**Fedora/RHEL:**
```bash
sudo dnf install mkvtoolnix
```

**macOS:**
```bash
brew install mkvtoolnix
```

**Windows:**
Download from [https://mkvtoolnix.download/](https://mkvtoolnix.download/)

## Installation

1. Clone or download this repository
2. Make the script executable (Linux/macOS):
```bash
chmod +x extract_subs.py
```

## Usage

Basic usage:
```bash
python extract_subs.py /path/to/tv/shows
```

Or if made executable:
```bash
./extract_subs.py /path/to/tv/shows
```

Overwrite existing subtitle files:
```bash
python extract_subs.py /path/to/tv/shows --overwrite
```

## Naming Convention

Extracted subtitles follow this naming pattern:

- Single English track: `{original_filename}.en.{extension}`
  - Example: `episode01.mkv` → `episode01.en.srt`

- Multiple English tracks: `{original_filename}.en.{track_number}.{extension}`
  - Example: `episode01.mkv` → `episode01.en.1.srt`, `episode01.en.2.srt`

## Output Example

```
Found 3 MKV file(s)

Processing: /media/tv/Show/Season 1/episode01.mkv
  Extracted: episode01.en.srt (English)

Processing: /media/tv/Show/Season 1/episode02.mkv
  Skipped: episode02.en.srt already exists

Processing: /media/tv/Show/Season 1/episode03.mkv
  Skipped: No English subtitles found

==================================================
SUMMARY
==================================================
Files processed:      3
Subtitles extracted:  1
Files skipped:        2
Errors encountered:   0
```

## Error Handling

The script handles various error scenarios:

- **Missing mkvtoolnix**: Exits with installation instructions
- **Invalid directory**: Exits with error message
- **Corrupted MKV files**: Logs error and continues with other files
- **Permission issues**: Logs error and continues with other files
- **Missing subtitle tracks**: Skips file and continues

## Command-line Options

```
positional arguments:
  directory      Directory containing MKV files (will search recursively)

optional arguments:
  -h, --help     Show help message and exit
  --overwrite    Overwrite existing subtitle files
```

## License

This script is provided as-is for personal use.
