"""Integration tests for Model._archive_previous_version_cache, real filesystem, no mocking."""

import os

import pytest

from dcmspec_explorer.model.model import Model


@pytest.fixture
def model(make_config, fake_logger):
    """Return a Model instance backed by a real, tmp_path-isolated Config."""
    return Model(config=make_config(), logger=fake_logger)


def _write_file(dir_path: str, file_name: str, content: str) -> None:
    """Create dir_path if needed and write content to file_name inside it."""
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, file_name), "w", encoding="utf-8") as f:
        f.write(content)


def _read_file(dir_path: str, file_name: str) -> str:
    """Return the content of file_name inside dir_path."""
    with open(os.path.join(dir_path, file_name), encoding="utf-8") as f:
        return f.read()


def _seed_standard_cache(model, content: str) -> str:
    """Write a ps3.3.html file with the given content into model's standard cache dir, return its path."""
    standard_dir = model._standard_cache_dir()
    _write_file(standard_dir, "ps3.3.html", content)
    return standard_dir


class TestArchivePreviousVersionCache:
    """Tests for Model._archive_previous_version_cache."""

    def test_moves_standard_and_model_dirs_into_versioned_folder(self, model):
        """cache/standard and cache/model are moved into cache/<version>/ when a version is set."""
        standard_dir = _seed_standard_cache(model, "standard content")
        model_dir = model._model_cache_dir()
        _write_file(model_dir, "Part3_table_A.2-1_expanded.json", "{}")
        model._version = "2025d"

        model._archive_previous_version_cache()

        assert not os.path.exists(standard_dir)
        assert not os.path.exists(model_dir)
        assert _read_file(model._versioned_standard_dir("2025d"), "ps3.3.html") == "standard content"
        assert os.path.exists(os.path.join(model._versioned_model_dir("2025d"), "Part3_table_A.2-1_expanded.json"))

    def test_renames_existing_versioned_dir_to_timestamped_backup_before_new_move(self, model):
        """A pre-existing cache/<version>/ archive is preserved under a timestamped backup dir."""
        model._version = "2025d"
        old_archive = model._versioned_dir("2025d")
        _write_file(old_archive, "sentinel.txt", "old archive")

        _seed_standard_cache(model, "new content")

        model._archive_previous_version_cache()

        # The new archive now holds the freshly moved standard folder.
        assert _read_file(model._versioned_standard_dir("2025d"), "ps3.3.html") == "new content"

        # The previous archive's content was preserved, not overwritten or lost.
        parent = os.path.dirname(old_archive)
        backup_dirs = [d for d in os.listdir(parent) if d.startswith("2025d_backup_")]
        assert len(backup_dirs) == 1
        assert _read_file(os.path.join(parent, backup_dirs[0]), "sentinel.txt") == "old archive"

    def test_noop_and_logs_info_when_no_previous_version(self, model, caplog):
        """With no previous version tracked, nothing is moved and an info message is logged."""
        model._version = None
        with caplog.at_level("INFO"):
            model._archive_previous_version_cache()
        assert "skipping cache move" in caplog.text.lower()

    def test_moves_only_existing_subdir_when_the_other_is_missing(self, model):
        """Only the standard or model subdir that actually exists is moved, the other is skipped."""
        _seed_standard_cache(model, "standard only")
        model._version = "2025d"

        model._archive_previous_version_cache()

        assert os.path.exists(os.path.join(model._versioned_standard_dir("2025d"), "ps3.3.html"))
        assert not os.path.exists(model._versioned_model_dir("2025d"))
