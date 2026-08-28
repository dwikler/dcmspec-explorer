"""Shared pytest fixtures for the dcmspec_explorer test suite."""

import pytest
from dcmspec.config import Config


@pytest.fixture(autouse=True)
def patch_dirs(monkeypatch, tmp_path):
    """Patch platformdirs lookups used by dcmspec.Config and app_config to pytest tmp_path."""
    cache_dir = tmp_path / "cache"
    config_dir = tmp_path / "config"
    monkeypatch.setattr("dcmspec.config.user_cache_dir", lambda app_name: str(cache_dir))
    monkeypatch.setattr("dcmspec.config.user_config_dir", lambda app_name: str(config_dir))
    monkeypatch.setattr("dcmspec_explorer.app_config.user_config_dir", lambda *a, **kw: str(config_dir))
    print(f"\ntest temp directory: {tmp_path}")  # visible with pytest -s
    return tmp_path


@pytest.fixture
def make_config():
    """Return a factory building a real dcmspec.config.Config rooted under pytest tmp_path."""

    def _make(config_file: str | None = None) -> Config:
        return Config(app_name="dcmspec_explorer_test", config_file=config_file)

    return _make
