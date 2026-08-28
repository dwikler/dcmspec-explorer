"""Integration tests for FavoritesManager's real filesystem persistence behavior."""

import json
import os

import pytest

from dcmspec_explorer.services.favorites_manager import FavoritesManager


@pytest.fixture
def config(make_config):
    """Return a real Config, shared by construction across FavoritesManager instances in a test."""
    return make_config()


class TestReloadAcrossInstances:
    """Tests that changes made by one FavoritesManager instance are visible to a new one."""

    def test_add_favorite_persists_and_is_visible_to_a_new_instance(self, config, fake_logger):
        """A favorite added by one instance is loaded by a second instance sharing the same config."""
        manager = FavoritesManager(config=config, logger=fake_logger)
        manager.add_favorite("table_A.1-1")

        reloaded = FavoritesManager(config=config, logger=fake_logger)
        assert reloaded.is_favorite("table_A.1-1") is True

    def test_remove_favorite_persists_the_removal(self, config, fake_logger):
        """A favorite removed by one instance stays removed for a second instance."""
        manager = FavoritesManager(config=config, logger=fake_logger)
        manager.add_favorite("table_A.1-1")
        manager.remove_favorite("table_A.1-1")

        reloaded = FavoritesManager(config=config, logger=fake_logger)
        assert reloaded.is_favorite("table_A.1-1") is False


class TestAtomicSave:
    """Tests for _save_favorites' write-temp-then-os.replace pattern."""

    def test_save_leaves_no_leftover_temp_file_and_writes_expected_json(self, config, fake_logger):
        """After a successful save, no .tmp file remains and the JSON has favorites + last_updated."""
        manager = FavoritesManager(config=config, logger=fake_logger)
        manager.add_favorite("table_A.1-1")

        assert not os.path.exists(f"{manager.favorites_file}.tmp")
        with open(manager.favorites_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["favorites"] == ["table_A.1-1"]
        assert "last_updated" in data


class TestCorruptionRecovery:
    """Tests for recovery from a malformed favorites.json on load."""

    def test_corrupted_file_is_backed_up_and_favorites_start_empty(self, config, fake_logger):
        """A malformed favorites.json is renamed to a timestamped .bak file, preserving its content."""
        favorites_file = os.path.join(os.path.dirname(config.config_file), "favorites.json")
        os.makedirs(os.path.dirname(favorites_file), exist_ok=True)
        with open(favorites_file, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        manager = FavoritesManager(config=config, logger=fake_logger)

        assert manager.get_favorites() == []
        assert not os.path.exists(favorites_file)
        backups = [
            name
            for name in os.listdir(os.path.dirname(favorites_file))
            if name.startswith("favorites.json.") and name.endswith(".bak")
        ]
        assert len(backups) == 1
        with open(os.path.join(os.path.dirname(favorites_file), backups[0]), encoding="utf-8") as f:
            assert f.read() == "{not valid json"


class TestSaveFailureDoesNotPropagate:
    """Tests that a failure during save is contained and doesn't leak a temp file or an exception."""

    def test_write_failure_leaves_no_temp_file_and_does_not_raise(self, config, fake_logger, monkeypatch):
        """A json.dump failure during save is caught, cleans up the .tmp file, and doesn't propagate."""
        manager = FavoritesManager(config=config, logger=fake_logger)

        def _raise_os_error(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("json.dump", _raise_os_error)

        manager.add_favorite("table_A.1-1")  # must not raise

        assert not os.path.exists(f"{manager.favorites_file}.tmp")
