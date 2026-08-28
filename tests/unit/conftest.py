"""Shared fixtures for unit tests (isolated collaborators, no real I/O beyond tmp_path)."""

import pytest


class DummyConfig:
    """Minimal stand-in for dcmspec.config.Config exposing only cache_dir/config_file."""

    def __init__(self, cache_dir, config_file):
        """Initialize the DummyConfig with the given cache_dir and config_file paths."""
        self.cache_dir = str(cache_dir)
        self.config_file = str(config_file)


@pytest.fixture
def dummy_config(tmp_path):
    """Return a DummyConfig rooted under tmp_path, with a config_file that doesn't exist yet."""
    return DummyConfig(cache_dir=tmp_path / "cache", config_file=tmp_path / "config" / "config.json")
