"""Shared utility helpers."""

import argparse


def positive_int(value: str) -> int:
    """argparse type validator: integer >= 1."""
    ivalue = int(value)
    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"threads must be >= 1, got {value}")
    return ivalue
