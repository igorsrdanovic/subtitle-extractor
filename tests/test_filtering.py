"""Tests for subtitle track filtering logic."""

import pytest
from subtitle_extractor.extractor import SubtitleExtractor


def _make_track(
    forced: bool = False,
    track_name: str = "",
    language: str = "en",
    codec: str = "subrip",
    track_id: int = 1,
) -> dict:
    return {
        "id": track_id,
        "codec": codec,
        "language": language,
        "forced": forced,
        "track_name": track_name,
    }


@pytest.fixture
def extractor() -> SubtitleExtractor:
    return SubtitleExtractor(languages=["en"])


class TestShouldSkipTrack:
    # ------------------------------------------------------------------
    # Forced tracks
    # ------------------------------------------------------------------

    def test_normal_track_not_skipped(self, extractor: SubtitleExtractor) -> None:
        skip, reason = extractor._should_skip_track(_make_track())
        assert skip is False
        assert reason == ""

    def test_forced_flag_skipped_by_default(self, extractor: SubtitleExtractor) -> None:
        skip, reason = extractor._should_skip_track(_make_track(forced=True))
        assert skip is True
        assert "forced" in reason

    def test_forced_in_name_skipped_by_default(self, extractor: SubtitleExtractor) -> None:
        skip, reason = extractor._should_skip_track(_make_track(track_name="Forced English"))
        assert skip is True
        assert "forced" in reason

    def test_forced_included_when_flag_set(self) -> None:
        ext = SubtitleExtractor(include_forced=True)
        skip, _ = ext._should_skip_track(_make_track(forced=True))
        assert skip is False

    # ------------------------------------------------------------------
    # SDH / CC
    # ------------------------------------------------------------------

    def test_sdh_in_name_skipped_by_default(self, extractor: SubtitleExtractor) -> None:
        for name in ("English SDH", "SDH English", "CC English", "Hearing Impaired"):
            skip, reason = extractor._should_skip_track(_make_track(track_name=name))
            assert skip is True, f"Expected skip for track_name={name!r}"
            assert reason  # non-empty

    def test_sdh_included_when_flag_set(self) -> None:
        ext = SubtitleExtractor(include_sdh=True)
        skip, _ = ext._should_skip_track(_make_track(track_name="English SDH"))
        assert skip is False

    # ------------------------------------------------------------------
    # Commentary
    # ------------------------------------------------------------------

    def test_commentary_not_excluded_by_default(self, extractor: SubtitleExtractor) -> None:
        skip, _ = extractor._should_skip_track(_make_track(track_name="Director Commentary"))
        assert skip is False

    def test_commentary_excluded_when_flag_set(self) -> None:
        ext = SubtitleExtractor(exclude_commentary=True)
        skip, reason = ext._should_skip_track(_make_track(track_name="Director Commentary"))
        assert skip is True
        assert "commentary" in reason

    def test_comment_substring_excluded(self) -> None:
        ext = SubtitleExtractor(exclude_commentary=True)
        skip, _ = ext._should_skip_track(_make_track(track_name="Author Comment"))
        assert skip is True

    # ------------------------------------------------------------------
    # Track title filter
    # ------------------------------------------------------------------

    def test_track_title_filter_matches(self) -> None:
        ext = SubtitleExtractor(track_title="english")
        skip, _ = ext._should_skip_track(_make_track(track_name="English Full"))
        assert skip is False

    def test_track_title_filter_no_match(self) -> None:
        ext = SubtitleExtractor(track_title="english")
        skip, reason = ext._should_skip_track(_make_track(track_name="Director Commentary"))
        assert skip is True
        assert "english" in reason

    def test_track_title_filter_case_insensitive(self) -> None:
        ext = SubtitleExtractor(track_title="ENGLISH")
        skip, _ = ext._should_skip_track(_make_track(track_name="English SDH"))
        # SDH check runs before title filter, so this should be skipped for SDH reason
        # Let's test with a non-SDH name
        skip, _ = ext._should_skip_track(_make_track(track_name="English Full"))
        assert skip is False
