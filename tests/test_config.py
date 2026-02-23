"""Tests for config loading and validation."""

import os
import textwrap
from pathlib import Path

import pytest
from subtitle_extractor.config import load_config, validate_config


class TestValidateConfig:
    def test_empty_config_ok(self) -> None:
        validate_config({})  # should not raise

    def test_all_valid_keys(self) -> None:
        validate_config({
            "languages": ["en", "es"],
            "overwrite": False,
            "dry_run": True,
            "threads": 4,
            "output_dir": "/tmp",
            "preserve_structure": True,
            "convert_to": "srt",
        })

    def test_unknown_key_exits(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit) as exc_info:
            validate_config({"unknown_key": "value"})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "unknown_key" in captured.err

    def test_multiple_unknown_keys_reported(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit):
            validate_config({"bad_a": 1, "bad_b": 2})
        captured = capsys.readouterr()
        assert "bad_a" in captured.err
        assert "bad_b" in captured.err

    def test_wrong_type_threads(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit) as exc_info:
            validate_config({"threads": "four"})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "threads" in captured.err

    def test_wrong_type_overwrite(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit):
            validate_config({"overwrite": "yes"})  # should be bool

    def test_threads_too_low(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit):
            validate_config({"threads": 0})
        captured = capsys.readouterr()
        assert "threads" in captured.err

    def test_threads_one_ok(self) -> None:
        validate_config({"threads": 1})

    def test_invalid_convert_to(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit):
            validate_config({"convert_to": "mkv"})
        captured = capsys.readouterr()
        assert "convert_to" in captured.err

    def test_valid_convert_to_values(self) -> None:
        validate_config({"convert_to": "srt"})
        validate_config({"convert_to": "ass"})

    def test_output_dir_not_a_dir(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        file_path = tmp_path / "not_a_dir.txt"
        file_path.touch()
        with pytest.raises(SystemExit):
            validate_config({"output_dir": str(file_path)})
        captured = capsys.readouterr()
        assert "output_dir" in captured.err

    def test_output_dir_valid_existing(self, tmp_path: Path) -> None:
        validate_config({"output_dir": str(tmp_path)})

    def test_output_dir_nonexistent_ok(self) -> None:
        # Non-existent paths are allowed (will be created at runtime).
        validate_config({"output_dir": "/nonexistent/path/that/does/not/exist"})


class TestLoadConfig:
    def test_no_config_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        result = load_config()
        assert result == {}

    def test_loads_local_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("yaml")
        config_file = tmp_path / ".subtitle-extractor.yaml"
        config_file.write_text(textwrap.dedent("""\
            languages:
              - en
              - fr
            threads: 2
        """))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        (tmp_path / "fakehome").mkdir()
        result = load_config()
        assert result["languages"] == ["en", "fr"]
        assert result["threads"] == 2

    def test_invalid_config_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("yaml")
        config_file = tmp_path / ".subtitle-extractor.yaml"
        config_file.write_text("bad_key: value\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        (tmp_path / "fakehome").mkdir()
        with pytest.raises(SystemExit):
            load_config()

    def test_empty_yaml_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("yaml")
        config_file = tmp_path / ".subtitle-extractor.yaml"
        config_file.write_text("")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        (tmp_path / "fakehome").mkdir()
        result = load_config()
        assert result == {}
