# sync-subs

Automatically detect and fix subtitle timing offset.

Your subtitles are a few seconds off? One command fixes them:

```sh
sync-subs movie.mkv subtitle.srt
```

That's it. `sync-subs` analyses the audio in your video, finds the timing
mismatch, and rewrites the subtitle file with corrected timestamps.

## Installation

```sh
pip install sync-subs
```

> **Requires:** Python 3.8+, [ffmpeg](https://ffmpeg.org/download.html) on your `PATH`.

## Usage

```
sync-subs VIDEO SUBTITLE [options]
```

| Command | What it does |
|---------|-------------|
| `sync-subs movie.mkv sub.srt` | Detect and fix in-place |
| `sync-subs movie.mkv sub.srt --check` | Report offset only, don't modify |
| `sync-subs movie.mkv sub.srt --output fixed.srt` | Write corrected subtitle to a new file |
| `sync-subs movie.mkv sub.srt --threshold 0.3` | Fix offsets >= 0.3 s (default: 0.5 s) |
| `sync-subs movie.mkv sub.srt --verbose` | Show confidence score |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | In sync (or successfully fixed) |
| `1` | Error (file not found, ffsubsync failed, …) |
| `2` | Offset detected above threshold (only when `--check` is used) |

The `--check` + exit code 2 pattern is useful in scripts:

```sh
if ! sync-subs movie.mkv sub.srt --check --threshold 1.0; then
    sync-subs movie.mkv sub.srt
fi
```

## How it works

`sync-subs` uses [ffsubsync](https://github.com/smacke/ffsubsync) under the
hood. It runs a Voice Activity Detection (VAD) pass over the video audio,
builds a speech-activity timeline, cross-correlates it against the subtitle
on/off timeline, and finds the offset where they best align.

The subtitle file is never modified until the correction succeeds — it writes
to a temporary file first and replaces the original atomically.

## Library usage

```python
from pathlib import Path
from sync_subs import check_sync, fix_sync

offset, confidence = check_sync(Path("movie.mkv"), Path("sub.srt"))
print(f"Offset: {offset:+.2f} s  (confidence: {confidence:.2f})")

if abs(offset) > 0.5 and confidence > 0.3:
    fixed = fix_sync(Path("movie.mkv"), Path("sub.srt"))
    print("Fixed!" if fixed else "Could not fix automatically.")
```

## License

MIT
