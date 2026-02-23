"""Tests for codec-to-extension mapping and output path generation."""

from pathlib import Path

import pytest
from subtitle_extractor.extractor import SubtitleExtractor


@pytest.fixture
def extractor() -> SubtitleExtractor:
    return SubtitleExtractor(languages=["en"])


class TestGetExtensionForCodec:
    def test_subrip(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("subrip") == "srt"

    def test_subrip_slash_srt(self, extractor: SubtitleExtractor) -> None:
        # mkvmerge may report codec as "SubRip/SRT"
        assert extractor.get_extension_for_codec("SubRip/SRT") == "srt"

    def test_ass(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("ass") == "ass"

    def test_ssa(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("ssa") == "ass"

    def test_pgs(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("hdmv_pgs_subtitle") == "sup"

    def test_vobsub(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("vobsub") == "sup"

    def test_mov_text(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("mov_text") == "srt"

    def test_tx3g(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("tx3g") == "srt"

    def test_unknown_defaults_to_srt(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("unknown_codec_xyz") == "srt"

    def test_case_insensitive_lookup(self, extractor: SubtitleExtractor) -> None:
        assert extractor.get_extension_for_codec("SUBRIP") == "srt"
        assert extractor.get_extension_for_codec("ASS") == "ass"

    def test_convert_to_overrides_text_codec(self) -> None:
        ext = SubtitleExtractor(convert_to="srt")
        assert ext.get_extension_for_codec("ass") == "srt"

    def test_convert_to_does_not_override_image_codec(self) -> None:
        ext = SubtitleExtractor(convert_to="srt")
        # Image-based codecs must be extracted natively first, then OCR'd.
        assert ext.get_extension_for_codec("hdmv_pgs_subtitle") == "sup"

    def test_convert_to_ass_overrides_srt_codec(self) -> None:
        ext = SubtitleExtractor(convert_to="ass")
        assert ext.get_extension_for_codec("subrip") == "ass"


class TestIsImageBasedCodec:
    def test_pgs_is_image(self, extractor: SubtitleExtractor) -> None:
        assert extractor._is_image_based_codec("hdmv_pgs_subtitle") is True

    def test_dvd_is_image(self, extractor: SubtitleExtractor) -> None:
        assert extractor._is_image_based_codec("dvd_subtitle") is True

    def test_vobsub_is_image(self, extractor: SubtitleExtractor) -> None:
        assert extractor._is_image_based_codec("vobsub") is True

    def test_srt_is_not_image(self, extractor: SubtitleExtractor) -> None:
        assert extractor._is_image_based_codec("subrip") is False

    def test_ass_is_not_image(self, extractor: SubtitleExtractor) -> None:
        assert extractor._is_image_based_codec("ass") is False


class TestGetOutputPath:
    def test_single_track_no_index(self, tmp_path: Path) -> None:
        ext = SubtitleExtractor(languages=["en"])
        video = tmp_path / "movie.mkv"
        out = ext._get_output_path(video, "en", "srt", index=0)
        assert out.name == "movie.en.srt"
        assert out.parent == tmp_path

    def test_multiple_tracks_with_index(self, tmp_path: Path) -> None:
        ext = SubtitleExtractor(languages=["en"])
        video = tmp_path / "movie.mkv"
        out = ext._get_output_path(video, "en", "srt", index=2)
        assert out.name == "movie.en.2.srt"

    def test_custom_output_dir_flat(self, tmp_path: Path) -> None:
        subs_dir = tmp_path / "subs"
        ext = SubtitleExtractor(languages=["en"], output_dir=subs_dir)
        video = tmp_path / "movies" / "movie.mkv"
        out = ext._get_output_path(video, "en", "srt", index=0)
        assert out.parent == subs_dir
        assert out.name == "movie.en.srt"
        # Directory should have been created.
        assert subs_dir.exists()

    def test_ass_extension(self, tmp_path: Path) -> None:
        ext = SubtitleExtractor(languages=["en"])
        video = tmp_path / "show.mkv"
        out = ext._get_output_path(video, "en", "ass", index=0)
        assert out.suffix == ".ass"

    def test_multiple_languages_separate_paths(self, tmp_path: Path) -> None:
        ext = SubtitleExtractor(languages=["en", "es"])
        video = tmp_path / "movie.mkv"
        en_out = ext._get_output_path(video, "en", "srt", index=0)
        es_out = ext._get_output_path(video, "es", "srt", index=0)
        assert en_out.name == "movie.en.srt"
        assert es_out.name == "movie.es.srt"
        assert en_out != es_out
