"""Unit tests for the pure in-memory logic of dcmspec_explorer.services.favorites_manager.FavoritesManager."""

import pytest

from dcmspec_explorer.model.model import IODEntry
from dcmspec_explorer.services.favorites_manager import FavoritesManager


@pytest.fixture
def favorites_manager(dummy_config, fake_logger):
    """Return a FavoritesManager backed by a DummyConfig whose favorites.json doesn't exist yet."""
    return FavoritesManager(config=dummy_config, logger=fake_logger)


class TestConstruction:
    """Tests for FavoritesManager.__init__ / _load_favorites when no favorites.json exists yet."""

    def test_starts_empty_when_no_favorites_file_exists(self, favorites_manager):
        """With no favorites.json on disk, the manager starts with zero favorites."""
        assert favorites_manager.get_favorites() == []
        assert favorites_manager.get_favorites_count() == 0


class TestIsFavorite:
    """Tests for FavoritesManager.is_favorite."""

    def test_true_for_a_known_favorite(self, favorites_manager):
        """A table_id present in the in-memory favorites set is reported as a favorite."""
        favorites_manager._favorites = {"table_A.1-1"}
        assert favorites_manager.is_favorite("table_A.1-1") is True

    def test_false_for_a_non_favorite(self, favorites_manager):
        """A table_id absent from the in-memory favorites set is not a favorite."""
        assert favorites_manager.is_favorite("table_A.1-1") is False


class TestGetFavorites:
    """Tests for FavoritesManager.get_favorites and get_favorites_count."""

    def test_get_favorites_returns_all_favorite_table_ids(self, favorites_manager):
        """get_favorites returns every table_id currently marked as a favorite."""
        favorites_manager._favorites = {"table_A.1-1", "table_B.1-1"}
        assert set(favorites_manager.get_favorites()) == {"table_A.1-1", "table_B.1-1"}

    def test_get_favorites_count_matches_number_of_favorites(self, favorites_manager):
        """get_favorites_count returns the size of the favorites set."""
        favorites_manager._favorites = {"table_A.1-1", "table_B.1-1"}
        assert favorites_manager.get_favorites_count() == 2


class TestFilterIodEntryList:
    """Tests for FavoritesManager.filter_iod_entry_list."""

    def test_returns_only_entries_marked_as_favorite(self, favorites_manager):
        """Only IODEntry objects whose table_id is a favorite are kept, in the original order."""
        favorites_manager._favorites = {"table_A.1-1"}
        entries = [
            IODEntry("Foo", "table_A.1-1", "http://example.com/a", "Composite"),
            IODEntry("Bar", "table_B.1-1", "http://example.com/b", "Normalized"),
        ]
        assert favorites_manager.filter_iod_entry_list(entries) == [entries[0]]
