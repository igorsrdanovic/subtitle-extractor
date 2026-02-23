"""Configuration loading and validation."""

import logging
import sys
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Valid configuration keys and their expected Python types.
_VALID_KEYS: Dict[str, type] = {
    "languages": list,
    "overwrite": bool,
    "dry_run": bool,
    "threads": int,
    "retries": int,
    "output_dir": str,
    "preserve_structure": bool,
    "convert_to": str,
    "check_sync": bool,
    "fix_sync": bool,
    "sync_threshold": float,
}

# Keys that accept both int and float values (e.g. `sync_threshold: 1` in YAML).
_NUMERIC_KEYS: frozenset = frozenset({"sync_threshold"})

_CONVERT_TO_VALUES = {"srt", "ass"}


def validate_config(config: Dict[str, Any]) -> None:
    """Validate *config* dict against known keys and types.

    Calls ``sys.exit(1)`` with a human-readable message on the first set of
    errors found so that the user sees all problems at once.
    """
    errors = []

    for key, value in config.items():
        if key not in _VALID_KEYS:
            errors.append(
                f"Unknown key '{key}'. Valid keys: {', '.join(sorted(_VALID_KEYS))}"
            )
            continue

        expected = _VALID_KEYS[key]
        # Numeric keys accept both int and float (e.g. `sync_threshold: 1` in YAML).
        if key in _NUMERIC_KEYS:
            if not isinstance(value, (int, float)):
                errors.append(
                    f"'{key}' must be a number, got {type(value).__name__}"
                )
        elif not isinstance(value, expected):
            errors.append(
                f"'{key}' must be {expected.__name__}, got {type(value).__name__}"
            )

    # Value-level checks (only when the type already passed).
    threads = config.get("threads")
    if isinstance(threads, int) and threads < 1:
        errors.append(f"'threads' must be >= 1, got {threads}")

    convert_to = config.get("convert_to")
    if isinstance(convert_to, str) and convert_to not in _CONVERT_TO_VALUES:
        errors.append(
            f"'convert_to' must be one of {sorted(_CONVERT_TO_VALUES)}, got '{convert_to}'"
        )

    output_dir = config.get("output_dir")
    if isinstance(output_dir, str):
        p = Path(output_dir)
        if p.exists() and not p.is_dir():
            errors.append(
                f"'output_dir' exists but is not a directory: {output_dir}"
            )

    sync_threshold = config.get("sync_threshold")
    if isinstance(sync_threshold, (int, float)) and sync_threshold < 0:
        errors.append(f"'sync_threshold' must be >= 0, got {sync_threshold}")

    if errors:
        print("Configuration error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)


def load_config() -> Dict[str, Any]:
    """Load and validate configuration from the first existing config file.

    Searches:
      1. ``~/.subtitle-extractor.yaml``
      2. ``.subtitle-extractor.yaml`` (current working directory)

    Returns an empty dict when no config file is found.
    """
    config_locations = [
        Path.home() / ".subtitle-extractor.yaml",
        Path(".subtitle-extractor.yaml"),
    ]

    for config_file in config_locations:
        if not config_file.exists():
            continue

        if not HAS_YAML:
            logging.warning(
                "YAML library not installed — config file ignored. "
                "Install with: pip install pyyaml"
            )
            break

        try:
            with open(config_file) as fh:
                config = yaml.safe_load(fh) or {}
            validate_config(config)  # exits on error
            logging.info(f"Loaded configuration from: {config_file}\n")
            return config
        except SystemExit:
            raise
        except Exception as exc:
            logging.warning(f"Could not load config from {config_file}: {exc}")
        break

    return {}
