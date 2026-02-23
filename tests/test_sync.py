"""Tests for subtitle sync detection (Phase 1: VAD via ffsubsync).

All tests are fully offline — no real video files or ffsubsync installation
required.  The ffsubsync pipeline is mocked at the module level so the tests
run in any CI environment.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from subtitle_extractor.extractor import SubtitleExtractor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_extractor(**kwargs) -> SubtitleExtractor:
    """Return a SubtitleExtractor targeting English with check_sync enabled."""
    return SubtitleExtractor(languages=["en"], check_sync=True, **kwargs)


# ---------------------------------------------------------------------------
# Tests for subtitle_extractor.sync module
# ---------------------------------------------------------------------------

class TestSyncModuleNotInstalled:
    """Graceful degradation when ffsubsync is absent."""

    def test_check_sync_returns_zeros(self, tmp_path: Path) -> None:
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", False):
            from subtitle_extractor import sync
            offset, confidence = sync.check_sync(
                tmp_path / "video.mkv",
                tmp_path / "sub.srt",
            )
        assert offset == 0.0
        assert confidence == 0.0

    def test_fix_sync_returns_false(self, tmp_path: Path) -> None:
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", False):
            from subtitle_extractor import sync
            result = sync.fix_sync(
                tmp_path / "video.mkv",
                tmp_path / "sub.srt",
            )
        assert result is False


# ---------------------------------------------------------------------------
# Tests for SubtitleExtractor._run_sync_check
# ---------------------------------------------------------------------------

class TestRunSyncCheckSkipping:
    """Image-based subtitle files must be silently skipped."""

    def test_sup_returns_none(self, tmp_path: Path) -> None:
        ext = _make_extractor()
        result = ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.sup")
        assert result is None

    def test_sub_returns_none(self, tmp_path: Path) -> None:
        ext = _make_extractor()
        result = ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.sub")
        assert result is None

    def test_returns_none_when_ffsubsync_not_installed(self, tmp_path: Path) -> None:
        ext = _make_extractor()
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", False):
            result = ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.srt")
        assert result is None


class TestRunSyncCheckStats:
    """sync_issues counter behaviour."""

    def test_counter_incremented_when_offset_above_threshold(self, tmp_path: Path) -> None:
        ext = SubtitleExtractor(languages=["en"], check_sync=True, sync_threshold=0.5)
        mock_check = MagicMock(return_value=(2.34, 0.9))
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check):
            ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.srt")
        assert ext.stats["sync_issues"] == 1

    def test_counter_not_incremented_when_below_threshold(self, tmp_path: Path) -> None:
        ext = SubtitleExtractor(languages=["en"], check_sync=True, sync_threshold=0.5)
        mock_check = MagicMock(return_value=(0.1, 0.9))
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check):
            ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.srt")
        assert ext.stats["sync_issues"] == 0

    def test_counter_not_incremented_on_low_confidence(self, tmp_path: Path) -> None:
        ext = SubtitleExtractor(languages=["en"], check_sync=True, sync_threshold=0.5)
        mock_check = MagicMock(return_value=(3.0, 0.1))
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check):
            ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.srt")
        # Low confidence means we report uncertainty, not a sync issue count.
        assert ext.stats["sync_issues"] == 0


class TestRunSyncCheckFixBehaviour:
    """Fix is applied only under the right conditions."""

    def test_fix_not_applied_when_below_threshold(self, tmp_path: Path) -> None:
        ext = SubtitleExtractor(
            languages=["en"], check_sync=True, fix_sync=True, sync_threshold=0.5
        )
        mock_check = MagicMock(return_value=(0.1, 0.9))
        mock_fix = MagicMock(return_value=True)
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check), \
             patch("subtitle_extractor.sync.fix_sync", mock_fix):
            ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.srt")
        mock_fix.assert_not_called()

    def test_fix_applied_when_above_threshold(self, tmp_path: Path) -> None:
        sub_file = tmp_path / "sub.srt"
        sub_file.write_text("dummy")
        ext = SubtitleExtractor(
            languages=["en"], check_sync=True, fix_sync=True, sync_threshold=0.5
        )
        mock_check = MagicMock(return_value=(2.34, 0.9))
        mock_fix = MagicMock(return_value=True)
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check), \
             patch("subtitle_extractor.sync.fix_sync", mock_fix):
            ext._run_sync_check(tmp_path / "video.mkv", sub_file)
        mock_fix.assert_called_once()

    def test_fix_not_applied_in_dry_run(self, tmp_path: Path) -> None:
        sub_file = tmp_path / "sub.srt"
        sub_file.write_text("dummy")
        ext = SubtitleExtractor(
            languages=["en"], check_sync=True, fix_sync=True,
            sync_threshold=0.5, dry_run=True,
        )
        mock_check = MagicMock(return_value=(2.34, 0.9))
        mock_fix = MagicMock(return_value=True)
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check), \
             patch("subtitle_extractor.sync.fix_sync", mock_fix):
            ext._run_sync_check(tmp_path / "video.mkv", sub_file)
        mock_fix.assert_not_called()

    def test_fix_not_applied_on_low_confidence(self, tmp_path: Path) -> None:
        sub_file = tmp_path / "sub.srt"
        sub_file.write_text("dummy")
        ext = SubtitleExtractor(
            languages=["en"], check_sync=True, fix_sync=True, sync_threshold=0.5
        )
        mock_check = MagicMock(return_value=(2.34, 0.1))
        mock_fix = MagicMock(return_value=True)
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check), \
             patch("subtitle_extractor.sync.fix_sync", mock_fix):
            ext._run_sync_check(tmp_path / "video.mkv", sub_file)
        mock_fix.assert_not_called()


class TestRunSyncCheckReturnValue:
    """Return value carries offset and confidence for the report."""

    def test_returns_offset_and_confidence(self, tmp_path: Path) -> None:
        ext = _make_extractor()
        mock_check = MagicMock(return_value=(1.5, 0.85))
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check):
            result = ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.srt")
        assert result is not None
        assert result[0] == pytest.approx(1.5)
        assert result[1] == pytest.approx(0.85)

    def test_returns_negative_offset_for_early_subtitles(self, tmp_path: Path) -> None:
        ext = _make_extractor()
        mock_check = MagicMock(return_value=(-1.0, 0.9))
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check):
            result = ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.srt")
        assert result is not None
        assert result[0] == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Tests for sync data in extraction result dict
# ---------------------------------------------------------------------------

class TestSyncFieldsInReport:
    """sync_offset and sync_confidence appear in the subtitle entry dict."""

    def test_sync_fields_added_when_check_sync_enabled(self, tmp_path: Path) -> None:
        ext = _make_extractor()
        mock_check = MagicMock(return_value=(2.0, 0.9))
        with patch("subtitle_extractor.sync.HAS_FFSUBSYNC", True), \
             patch("subtitle_extractor.sync.check_sync", mock_check):
            sync_result = ext._run_sync_check(tmp_path / "video.mkv", tmp_path / "sub.srt")

        assert sync_result is not None
        sub_entry = {"output": str(tmp_path / "sub.srt"), "language": "en"}
        sub_entry["sync_offset"] = sync_result[0]
        sub_entry["sync_confidence"] = sync_result[1]

        assert "sync_offset" in sub_entry
        assert "sync_confidence" in sub_entry
        assert sub_entry["sync_offset"] == pytest.approx(2.0)
        assert sub_entry["sync_confidence"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Tests for config validation of sync keys
# ---------------------------------------------------------------------------

class TestSyncConfigValidation:
    """New config keys pass validation correctly."""

    def test_check_sync_bool_valid(self) -> None:
        from subtitle_extractor.config import validate_config
        validate_config({"check_sync": True})  # should not raise

    def test_fix_sync_bool_valid(self) -> None:
        from subtitle_extractor.config import validate_config
        validate_config({"fix_sync": False})  # should not raise

    def test_sync_threshold_float_valid(self) -> None:
        from subtitle_extractor.config import validate_config
        validate_config({"sync_threshold": 1.0})  # should not raise

    def test_sync_threshold_int_valid(self) -> None:
        # YAML may parse `1` as int; config should accept this.
        from subtitle_extractor.config import validate_config
        validate_config({"sync_threshold": 1})  # should not raise

    def test_sync_threshold_zero_valid(self) -> None:
        from subtitle_extractor.config import validate_config
        validate_config({"sync_threshold": 0.0})  # should not raise

    def test_sync_threshold_negative_invalid(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        from subtitle_extractor.config import validate_config
        with pytest.raises(SystemExit) as exc_info:
            validate_config({"sync_threshold": -0.5})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "sync_threshold" in captured.err

    def test_check_sync_wrong_type_invalid(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        from subtitle_extractor.config import validate_config
        with pytest.raises(SystemExit):
            validate_config({"check_sync": "yes"})  # must be bool
        captured = capsys.readouterr()
        assert "check_sync" in captured.err


# ---------------------------------------------------------------------------
# Tests for SubtitleExtractor.__init__ sync parameters
# ---------------------------------------------------------------------------

class TestExtractorSyncInit:
    """Sync parameters are stored correctly on the extractor instance."""

    def test_defaults(self) -> None:
        ext = SubtitleExtractor(languages=["en"])
        assert ext.check_sync is False
        assert ext.fix_sync is False
        assert ext.sync_threshold == pytest.approx(0.5)

    def test_custom_values(self) -> None:
        ext = SubtitleExtractor(
            languages=["en"], check_sync=True, fix_sync=True, sync_threshold=1.5
        )
        assert ext.check_sync is True
        assert ext.fix_sync is True
        assert ext.sync_threshold == pytest.approx(1.5)

    def test_negative_threshold_clamped_to_zero(self) -> None:
        ext = SubtitleExtractor(languages=["en"], sync_threshold=-1.0)
        assert ext.sync_threshold == pytest.approx(0.0)

    def test_sync_issues_in_stats(self) -> None:
        ext = SubtitleExtractor(languages=["en"])
        assert "sync_issues" in ext.stats
        assert ext.stats["sync_issues"] == 0
