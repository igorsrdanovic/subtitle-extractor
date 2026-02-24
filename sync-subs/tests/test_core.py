"""Tests for sync_subs.core — subtitle sync detection and correction.

All tests are fully offline — no real video files or ffsubsync installation
required. The ffsubsync pipeline is mocked at the module level so the tests
run in any CI environment.
"""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sync_subs.core import check_sync, fix_sync


# ---------------------------------------------------------------------------
# Graceful degradation when ffsubsync is absent
# ---------------------------------------------------------------------------

class TestSyncModuleNotInstalled:
    """check_sync and fix_sync degrade gracefully when ffsubsync is absent."""

    def test_check_sync_returns_zeros(self, tmp_path: Path) -> None:
        with patch("sync_subs.core.HAS_FFSUBSYNC", False):
            offset, confidence = check_sync(
                tmp_path / "video.mkv",
                tmp_path / "sub.srt",
            )
        assert offset == 0.0
        assert confidence == 0.0

    def test_fix_sync_returns_false(self, tmp_path: Path) -> None:
        with patch("sync_subs.core.HAS_FFSUBSYNC", False):
            result = fix_sync(
                tmp_path / "video.mkv",
                tmp_path / "sub.srt",
            )
        assert result is False


# ---------------------------------------------------------------------------
# check_sync return values
# ---------------------------------------------------------------------------

class TestCheckSync:
    """check_sync returns (offset, confidence) from ffsubsync result dict."""

    def _mock_run(self, offset: float, sync_ok: bool):
        """Return a mock _ffsubsync_run that produces the given result."""
        mock = MagicMock(return_value={
            "offset_seconds": offset,
            "sync_was_successful": sync_ok,
        })
        return mock

    def test_positive_offset_late_subtitles(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub.srt"
        sub.write_text("dummy")
        mock_run = self._mock_run(2.34, True)
        with patch("sync_subs.core.HAS_FFSUBSYNC", True), \
             patch("sync_subs.core._ffsubsync_run", mock_run), \
             patch("sync_subs.core.make_parser") as mock_parser:
            mock_parser.return_value.parse_args.return_value = MagicMock()
            offset, confidence = check_sync(tmp_path / "video.mkv", sub)
        assert offset == pytest.approx(2.34)
        assert confidence == pytest.approx(0.9)

    def test_negative_offset_early_subtitles(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub.srt"
        sub.write_text("dummy")
        mock_run = self._mock_run(-1.0, True)
        with patch("sync_subs.core.HAS_FFSUBSYNC", True), \
             patch("sync_subs.core._ffsubsync_run", mock_run), \
             patch("sync_subs.core.make_parser") as mock_parser:
            mock_parser.return_value.parse_args.return_value = MagicMock()
            offset, confidence = check_sync(tmp_path / "video.mkv", sub)
        assert offset == pytest.approx(-1.0)
        assert confidence == pytest.approx(0.9)

    def test_low_confidence_when_sync_not_successful(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub.srt"
        sub.write_text("dummy")
        mock_run = self._mock_run(0.5, False)
        with patch("sync_subs.core.HAS_FFSUBSYNC", True), \
             patch("sync_subs.core._ffsubsync_run", mock_run), \
             patch("sync_subs.core.make_parser") as mock_parser:
            mock_parser.return_value.parse_args.return_value = MagicMock()
            _, confidence = check_sync(tmp_path / "video.mkv", sub)
        assert confidence == pytest.approx(0.2)

    def test_returns_zeros_on_exception(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub.srt"
        sub.write_text("dummy")
        with patch("sync_subs.core.HAS_FFSUBSYNC", True), \
             patch("sync_subs.core._ffsubsync_run", side_effect=RuntimeError("boom")), \
             patch("sync_subs.core.make_parser") as mock_parser:
            mock_parser.return_value.parse_args.return_value = MagicMock()
            offset, confidence = check_sync(tmp_path / "video.mkv", sub)
        assert offset == 0.0
        assert confidence == 0.0


# ---------------------------------------------------------------------------
# fix_sync behaviour
# ---------------------------------------------------------------------------

class TestFixSync:
    """fix_sync atomically rewrites the subtitle file on success."""

    def _mock_run_success(self, tmp_path_arg):
        """Return a mock that writes a temp file and returns retval=0."""
        def _run(args):
            # Write something to the output path that ffsubsync would write to.
            Path(args.output).write_text("corrected content")
            return {"retval": 0}
        return _run

    def test_returns_true_on_success(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub.srt"
        sub.write_text("original")
        # Pin the temp path so mock_run can write to it and fix_sync can find it.
        known_tmp = str(tmp_path / "known_tmp.srt")

        def mock_run(args):
            Path(known_tmp).write_text("corrected")
            return {"retval": 0}

        with patch("sync_subs.core.HAS_FFSUBSYNC", True), \
             patch("sync_subs.core._ffsubsync_run", mock_run), \
             patch("sync_subs.core.make_parser") as mock_parser, \
             patch("sync_subs.core.tempfile.mktemp", return_value=known_tmp):
            mock_parser.return_value.parse_args.return_value = MagicMock()
            result = fix_sync(tmp_path / "video.mkv", sub)
        assert result is True

    def test_returns_false_when_retval_nonzero(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub.srt"
        sub.write_text("original")
        mock_run = MagicMock(return_value={"retval": 1})
        with patch("sync_subs.core.HAS_FFSUBSYNC", True), \
             patch("sync_subs.core._ffsubsync_run", mock_run), \
             patch("sync_subs.core.make_parser") as mock_parser:
            mock_parser.return_value.parse_args.return_value = MagicMock()
            result = fix_sync(tmp_path / "video.mkv", sub)
        assert result is False

    def test_returns_false_on_exception(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub.srt"
        sub.write_text("original")
        with patch("sync_subs.core.HAS_FFSUBSYNC", True), \
             patch("sync_subs.core._ffsubsync_run", side_effect=RuntimeError("boom")), \
             patch("sync_subs.core.make_parser") as mock_parser:
            mock_parser.return_value.parse_args.return_value = MagicMock()
            result = fix_sync(tmp_path / "video.mkv", sub)
        assert result is False


# ---------------------------------------------------------------------------
# CLI integration (argument parsing and exit codes)
# ---------------------------------------------------------------------------

class TestCLI:
    """CLI exits with correct codes and handles --check / --output flags."""

    def _run(self, args, mock_check=None, mock_fix=None):
        """Run cli.main() with patched core functions, return SystemExit code."""
        from sync_subs import cli

        default_check = MagicMock(return_value=(0.0, 0.9))
        default_fix = MagicMock(return_value=True)

        with patch("sync_subs.cli.HAS_FFSUBSYNC", True), \
             patch("sync_subs.cli.check_sync", mock_check or default_check), \
             patch("sync_subs.cli.fix_sync", mock_fix or default_fix), \
             patch("sys.argv", ["sync-subs"] + args):
            with pytest.raises(SystemExit) as exc_info:
                cli.main()
            return exc_info.value.code

    def test_in_sync_exits_0(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mkv"
        sub = tmp_path / "s.srt"
        video.write_text("x")
        sub.write_text("x")
        code = self._run(
            [str(video), str(sub), "--check"],
            mock_check=MagicMock(return_value=(0.1, 0.9)),
        )
        assert code == 0

    def test_check_offset_above_threshold_exits_2(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mkv"
        sub = tmp_path / "s.srt"
        video.write_text("x")
        sub.write_text("x")
        code = self._run(
            [str(video), str(sub), "--check"],
            mock_check=MagicMock(return_value=(2.34, 0.9)),
        )
        assert code == 2

    def test_fix_success_exits_0(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mkv"
        sub = tmp_path / "s.srt"
        video.write_text("x")
        sub.write_text("x")
        code = self._run(
            [str(video), str(sub)],
            mock_check=MagicMock(return_value=(2.34, 0.9)),
            mock_fix=MagicMock(return_value=True),
        )
        assert code == 0

    def test_fix_failure_exits_1(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mkv"
        sub = tmp_path / "s.srt"
        video.write_text("x")
        sub.write_text("x")
        code = self._run(
            [str(video), str(sub)],
            mock_check=MagicMock(return_value=(2.34, 0.9)),
            mock_fix=MagicMock(return_value=False),
        )
        assert code == 1

    def test_output_flag_writes_to_output_path(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mkv"
        sub = tmp_path / "s.srt"
        out = tmp_path / "fixed.srt"
        video.write_text("x")
        sub.write_text("original content")

        def mock_fix(video_file, subtitle_file):
            # Simulate fix_sync succeeding on whatever file it's given.
            return True

        code = self._run(
            [str(video), str(sub), "--output", str(out)],
            mock_check=MagicMock(return_value=(2.0, 0.9)),
            mock_fix=mock_fix,
        )
        assert code == 0
        assert out.exists()

    def test_missing_video_exits_1(self, tmp_path: Path) -> None:
        sub = tmp_path / "s.srt"
        sub.write_text("x")
        code = self._run([str(tmp_path / "nonexistent.mkv"), str(sub)])
        assert code == 1

    def test_missing_subtitle_exits_1(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mkv"
        video.write_text("x")
        code = self._run([str(video), str(tmp_path / "nonexistent.srt")])
        assert code == 1

    def test_check_and_output_mutually_exclusive_exits_1(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mkv"
        sub = tmp_path / "s.srt"
        out = tmp_path / "fixed.srt"
        video.write_text("x")
        sub.write_text("x")
        code = self._run(
            [str(video), str(sub), "--check", "--output", str(out)]
        )
        assert code == 1
