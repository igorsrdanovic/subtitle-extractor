# MKV/MP4 Subtitle Extractor

A Python script that recursively extracts subtitles from MKV and MP4 files in multiple languages and saves them in the same directory as the source files.

## Features

### Core Features
- Recursively processes all MKV and MP4 files in a directory
- **Multi-language support**: Extract subtitles in one or more languages
- Supports 25+ languages with automatic code normalization (ISO 639-1, ISO 639-2, or language names)
- Automatically detects subtitle codec and uses appropriate extension:
  - SubRip/SRT → `.srt`
  - ASS/SSA → `.ass`
  - PGS/VobSub → `.sup`
  - MP4 text/mov_text → `.srt`
- Skips files that already have extracted subtitles
- Handles multiple subtitle tracks per language
- **Real-time progress tracking**: Shows files completed, remaining, and percentage
- Robust error handling

### Advanced Features
- **Dry-Run Mode**: Preview what would be extracted without making changes
- **Parallel Processing**: Extract from multiple files simultaneously (multi-threading)
- **Configuration File**: Save default settings in `.subtitle-extractor.yaml`
- **Advanced Filtering**: Filter by forced/SDH/commentary tracks and track titles
- **Logging & Reports**: Save detailed logs and generate JSON/CSV reports
- **Subtitle Conversion**: Convert all subtitles to SRT or ASS format
- **Output Directory Control**: Extract to separate directory with optional structure preservation
- **Resume Capability**: Continue from where you left off if interrupted

## Requirements

- Python 3.6 or higher
- **For MKV files**: mkvtoolnix (`mkvmerge` and `mkvextract`)
- **For MP4 files**: ffmpeg (`ffmpeg` and `ffprobe`)

**Note:** You need at least one of these tools installed. If you only have mkvtoolnix, the script will only process MKV files. If you only have ffmpeg, it will only process MP4 files.

### Installing mkvtoolnix (for MKV support)

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

### Installing ffmpeg (for MP4 support)

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**Fedora/RHEL:**
```bash
sudo dnf install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)

## Installation

1. Clone or download this repository
2. Make the script executable (Linux/macOS):
```bash
chmod +x extract_subs.py
```

## Usage

### Basic Usage

Extract English subtitles (default):
```bash
python extract_subs.py /path/to/tv/shows
```

Or if made executable:
```bash
./extract_subs.py /path/to/tv/shows
```

### Extract Specific Languages

Extract Spanish subtitles:
```bash
python extract_subs.py /path/to/videos --languages es
# or
python extract_subs.py /path/to/videos --languages spa
# or
python extract_subs.py /path/to/videos --languages spanish
```

Extract multiple languages (English, Spanish, and French):
```bash
python extract_subs.py /path/to/videos --languages en es fr
```

### Other Options

Overwrite existing subtitle files:
```bash
python extract_subs.py /path/to/tv/shows --overwrite
```

Combine language selection with overwrite:
```bash
python extract_subs.py /path/to/videos --languages en fr --overwrite
```

## Advanced Usage

### Dry-Run Mode
Preview what would be extracted without making any changes:
```bash
python extract_subs.py /path/to/videos --dry-run
```

### Parallel Processing
Use multiple threads for faster processing:
```bash
python extract_subs.py /path/to/videos --threads 4
```

### Output Directory
Extract subtitles to a separate directory:
```bash
# Flat structure
python extract_subs.py /path/to/videos --output-dir /path/to/subtitles

# Preserve directory structure
python extract_subs.py /path/to/videos --output-dir /path/to/subtitles --preserve-structure
```

### Subtitle Conversion
Convert all extracted subtitles to SRT format:
```bash
python extract_subs.py /path/to/videos --convert-to srt
```

### Advanced Filtering
```bash
# Include forced subtitles
python extract_subs.py /path/to/videos --include-forced

# Include SDH/hearing impaired subtitles
python extract_subs.py /path/to/videos --include-sdh

# Exclude commentary tracks
python extract_subs.py /path/to/videos --exclude-commentary

# Filter by track title
python extract_subs.py /path/to/videos --track-title "English"
```

### Logging and Reports
```bash
# Save log to file
python extract_subs.py /path/to/videos --log-file extraction.log

# Generate JSON report
python extract_subs.py /path/to/videos --report-format json

# Generate CSV report
python extract_subs.py /path/to/videos --report-format csv
```

### Resume Capability
If extraction is interrupted, resume from where you left off:
```bash
python extract_subs.py /path/to/videos --resume
```

### Configuration File
Create `~/.subtitle-extractor.yaml` with default settings:
```yaml
languages:
  - en
  - es
overwrite: false
threads: 4
output_dir: /path/to/subtitles
preserve_structure: true
```

Then run without specifying options:
```bash
python extract_subs.py /path/to/videos
```

### Combined Example
```bash
python extract_subs.py /path/to/videos \
  --languages en es fr \
  --threads 4 \
  --output-dir /path/to/subs \
  --preserve-structure \
  --convert-to srt \
  --exclude-commentary \
  --report-format json \
  --resume
```

### Supported Languages

The script supports 25+ languages with flexible input formats:

| Language | ISO 639-1 | ISO 639-2 | Name |
|----------|-----------|-----------|------|
| English | `en` | `eng` | `english` |
| Spanish | `es` | `spa` | `spanish` |
| French | `fr` | `fra`, `fre` | `french` |
| German | `de` | `deu`, `ger` | `german` |
| Italian | `it` | `ita` | `italian` |
| Portuguese | `pt` | `por` | `portuguese` |
| Russian | `ru` | `rus` | `russian` |
| Japanese | `ja` | `jpn` | `japanese` |
| Chinese | `zh` | `zho`, `chi` | `chinese` |
| Korean | `ko` | `kor` | `korean` |
| Arabic | `ar` | `ara` | `arabic` |
| Hindi | `hi` | `hin` | `hindi` |
| Dutch | `nl` | `nld`, `dut` | `dutch` |
| Polish | `pl` | `pol` | `polish` |
| Swedish | `sv` | `swe` | `swedish` |
| Norwegian | `no` | `nor` | `norwegian` |
| Danish | `da` | `dan` | `danish` |
| Finnish | `fi` | `fin` | `finnish` |
| Turkish | `tr` | `tur` | `turkish` |
| Greek | `el` | `ell`, `gre` | `greek` |
| Hebrew | `he` | `heb` | `hebrew` |
| Czech | `cs` | `ces`, `cze` | `czech` |
| Hungarian | `hu` | `hun` | `hungarian` |
| Romanian | `ro` | `ron`, `rum` | `romanian` |
| Thai | `th` | `tha` | `thai` |
| Vietnamese | `vi` | `vie` | `vietnamese` |

**Note:** You can use any of the three formats interchangeably. The script automatically normalizes them.

## Naming Convention

Extracted subtitles follow this naming pattern using ISO 639-1 language codes:

- Single subtitle track per language: `{original_filename}.{lang}.{extension}`
  - Example: `episode01.mkv` → `episode01.en.srt`
  - Example: `movie.mp4` → `movie.es.srt`

- Multiple subtitle tracks for the same language: `{original_filename}.{lang}.{track_number}.{extension}`
  - Example: `episode01.mkv` → `episode01.en.1.srt`, `episode01.en.2.srt`
  - Example: `movie.mp4` → `movie.fr.1.srt`, `movie.fr.2.srt`

**Language codes in filenames** always use the ISO 639-1 format (2 letters), regardless of which format you use in the command.

## Output Examples

### Example 1: Extract English subtitles (default)

```bash
$ python extract_subs.py /media/tv/Show
Extracting subtitles for: en

Found 2 MKV file(s) and 0 MP4 file(s)

Processing: /media/tv/Show/Season 1/episode01.mkv
  Extracted: episode01.en.srt
  Progress: 1/2 files completed (50.0%) | 1 remaining

Processing: /media/tv/Show/Season 1/episode02.mkv
  Skipped: episode02.en.srt already exists
  Progress: 2/2 files completed (100.0%) | 0 remaining

==================================================
SUMMARY
==================================================
Files processed:      2
Subtitles extracted:  1
Files skipped:        1
Errors encountered:   0
```

### Example 2: Extract multiple languages

```bash
$ python extract_subs.py /media/movies --languages en es fr
Extracting subtitles for: en, es, fr

Found 0 MKV file(s) and 2 MP4 file(s)

Processing: /media/movies/movie1.mp4
  Extracted: movie1.en.srt
  Extracted: movie1.es.srt
  Extracted: movie1.fr.srt
  Progress: 1/2 files completed (50.0%) | 1 remaining

Processing: /media/movies/movie2.mp4
  Skipped: No subtitles found for language(s): en, es, fr
  Progress: 2/2 files completed (100.0%) | 0 remaining

==================================================
SUMMARY
==================================================
Files processed:      2
Subtitles extracted:  3
Files skipped:        1
Errors encountered:   0
```

## Error Handling

The script handles various error scenarios:

- **Missing both tools**: Exits with installation instructions for both mkvtoolnix and ffmpeg
- **Missing one tool**: Shows warning and continues (only processes supported file types)
- **Invalid directory**: Exits with error message
- **Corrupted video files**: Logs error and continues with other files
- **Permission issues**: Logs error and continues with other files
- **Missing subtitle tracks**: Skips file and continues

## Command-line Options

```
positional arguments:
  directory                         Directory containing video files (will search recursively)

optional arguments:
  -h, --help                        Show help message and exit
  -l LANG [LANG ...], --languages LANG [LANG ...]
                                    Language codes to extract (default: en)
  --overwrite                       Overwrite existing subtitle files
  --dry-run                         Preview without making changes
  --threads N                       Number of parallel threads (default: 1)
  --include-forced                  Include forced subtitles
  --include-sdh                     Include SDH/hearing impaired subtitles
  --exclude-commentary              Exclude commentary tracks
  --track-title TITLE               Filter by track title (substring match)
  --log-file FILE                   Save log to file
  --report-format {json,csv}        Generate extraction report
  --convert-to {srt,ass}            Convert all subtitles to format
  --output-dir DIR                  Extract to specified directory
  --preserve-structure              Preserve directory structure in output
  --resume                          Resume from previous run
```

### Quick Reference

```bash
# Default (English only)
python extract_subs.py /path/to/videos

# Single language
python extract_subs.py /path/to/videos --languages es

# Multiple languages
python extract_subs.py /path/to/videos --languages en es fr de

# Short form
python extract_subs.py /path/to/videos -l en fr

# With overwrite
python extract_subs.py /path/to/videos -l en es --overwrite

# Dry-run (preview)
python extract_subs.py /path/to/videos --dry-run

# Fast parallel processing
python extract_subs.py /path/to/videos --threads 4

# Extract to separate directory
python extract_subs.py /path/to/videos --output-dir /path/to/subs

# Convert all to SRT
python extract_subs.py /path/to/videos --convert-to srt

# Resume interrupted run
python extract_subs.py /path/to/videos --resume
```

## License

This script is provided as-is for personal use.
