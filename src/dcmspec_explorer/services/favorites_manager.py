"""Favorites Management class for DCMspec Explorer."""

from typing import Set
import json
import os
from datetime import datetime


class FavoritesManager:
    """Manages the persistent list of user favorites (DICOM IODs) for DCMspec Explorer.

    This class provides methods to add, remove, check, and retrieve favorite IOD table IDs.
    Favorites are stored in a JSON file (favorites.json) in the same directory as the main
    application config file.


    Args:
        config: The application configuration.
        logger: An optional logger for logging events.

    """

    def __init__(self, config, logger=None):
        """Initialize the FavoritesManager."""
        self.config = config
        self.logger = logger

        # Use the directory of the config file for persistent user data
        config_dir = os.path.dirname(self.config.config_file)
        self.favorites_file = os.path.join(config_dir, "favorites.json")

        # Initialize an empty set for favorites IODs table IDs
        self._favorites: Set[str] = set()
        self._load_favorites()

    def _load_favorites(self):
        """Load favorites from the favorites JSON file in the user's config directory."""
        if os.path.exists(self.favorites_file):
            try:
                with open(self.favorites_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._favorites = set(data.get("favorites", []))
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Failed to load favorites: {e}")
                self._favorites = set()
        else:
            self._favorites = set()

    def _save_favorites(self):
        """Save favorites to the favorites JSON file in the user's config directory."""
        data = {
            "favorites": list(self._favorites),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        }
        try:
            os.makedirs(os.path.dirname(self.favorites_file), exist_ok=True)
            with open(self.favorites_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to save favorites: {e}")

    def is_favorite(self, table_id: str) -> bool:
        """Check if a given table_id is marked as favorite."""
        return table_id in self._favorites

    def add_favorite(self, table_id: str):
        """Add a table_id to the favorites."""
        self._favorites.add(table_id)
        self._save_favorites()
        if self.logger:
            self.logger.info(f"Added favorite: {table_id}")

    def remove_favorite(self, table_id: str):
        """Remove a table_id from the favorites."""
        self._favorites.discard(table_id)
        self._save_favorites()
        if self.logger:
            self.logger.info(f"Removed favorite: {table_id}")

    def get_favorites(self):
        """Get a list of all favorite table_ids."""
        return list(self._favorites)

    def filter_iod_entry_list(self, iod_entry_list):
        """Return a list of IODEntry objects that are marked as favorites.

        Args:
            iod_entry_list (Iterable[IODEntry]): List or iterable of IODEntry objects.

        Returns:
            List[IODEntry]: Only those entries whose table_id is a favorite.

        """
        return [iod for iod in iod_entry_list if iod.table_id in self._favorites]

    def get_favorites_count(self):
        """Get the count of favorite table_ids."""
        return len(self._favorites)
