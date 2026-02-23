"""Tests for language code normalisation and matching."""

import pytest
from subtitle_extractor.extractor import SubtitleExtractor


@pytest.fixture
def extractor() -> SubtitleExtractor:
    """Default extractor targeting English."""
    return SubtitleExtractor(languages=["en"])


class TestNormalizeLanguages:
    def test_iso_639_1_passthrough(self, extractor: SubtitleExtractor) -> None:
        assert extractor._normalize_languages(["en"]) == ["en"]

    def test_iso_639_2_three_letter(self, extractor: SubtitleExtractor) -> None:
        assert extractor._normalize_languages(["eng"]) == ["en"]

    def test_full_name_english(self, extractor: SubtitleExtractor) -> None:
        assert extractor._normalize_languages(["english"]) == ["en"]

    def test_case_insensitive(self, extractor: SubtitleExtractor) -> None:
        assert extractor._normalize_languages(["English"]) == ["en"]
        assert extractor._normalize_languages(["ENGLISH"]) == ["en"]
        assert extractor._normalize_languages(["ENG"]) == ["en"]

    def test_multiple_languages_sorted(self, extractor: SubtitleExtractor) -> None:
        result = extractor._normalize_languages(["eng", "spa", "fre"])
        assert result == sorted(result), "result should be sorted"
        assert "en" in result
        assert "es" in result
        assert "fr" in result

    def test_deduplication(self, extractor: SubtitleExtractor) -> None:
        result = extractor._normalize_languages(["en", "eng", "english"])
        assert result.count("en") == 1

    def test_unknown_code_passes_through(self, extractor: SubtitleExtractor) -> None:
        result = extractor._normalize_languages(["xyz"])
        assert "xyz" in result

    def test_various_language_codes(self, extractor: SubtitleExtractor) -> None:
        pairs = [
            ("spa", "es"), ("fre", "fr"), ("fra", "fr"), ("ger", "de"),
            ("deu", "de"), ("ita", "it"), ("por", "pt"), ("rus", "ru"),
            ("jpn", "ja"), ("chi", "zh"), ("zho", "zh"), ("kor", "ko"),
        ]
        for code, expected in pairs:
            result = extractor._normalize_languages([code])
            assert expected in result, f"{code!r} should normalise to {expected!r}"


class TestMatchesLanguage:
    def test_match_by_iso_639_1(self, extractor: SubtitleExtractor) -> None:
        matches, normalized = extractor._matches_language("en")
        assert matches is True
        assert normalized == "en"

    def test_match_by_iso_639_2(self, extractor: SubtitleExtractor) -> None:
        matches, normalized = extractor._matches_language("eng")
        assert matches is True
        assert normalized == "en"

    def test_no_match_other_language(self, extractor: SubtitleExtractor) -> None:
        matches, _ = extractor._matches_language("spa")  # extractor targets 'en' only
        assert matches is False

    def test_empty_string(self, extractor: SubtitleExtractor) -> None:
        matches, normalized = extractor._matches_language("")
        assert matches is False
        assert normalized == ""

    def test_case_insensitive_match(self, extractor: SubtitleExtractor) -> None:
        matches, _ = extractor._matches_language("ENG")
        assert matches is True

    def test_multi_language_extractor(self) -> None:
        ext = SubtitleExtractor(languages=["en", "es", "fr"])
        for code in ("en", "eng", "spa", "fre", "fra"):
            matches, _ = ext._matches_language(code)
            assert matches is True, f"{code!r} should match"
