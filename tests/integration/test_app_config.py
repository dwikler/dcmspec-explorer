"""Integration tests for dcmspec_explorer.app_config, exercising the real filesystem/env/platformdirs boundary."""

import json
import logging

import pytest

from dcmspec_explorer.app_config import load_app_config, setup_logger


def _write_json(path, data):
    """Write data as JSON to path, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _seed_cwd_config(monkeypatch, tmp_path, data):
    """Write a dcmspec_explorer_config.json into a fresh cwd dir and chdir into it."""
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    _write_json(cwd_dir / "dcmspec_explorer_config.json", data)
    monkeypatch.chdir(cwd_dir)


@pytest.fixture
def project_root(monkeypatch, tmp_path):
    """Point find_project_root at an isolated tmp_path layout instead of the real repo's own config/ dir."""
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr("dcmspec_explorer.app_config.find_project_root", lambda marker="pyproject.toml": root)
    return root


@pytest.fixture(autouse=True)
def clean_app_logger():
    """Clear the shared, process-wide "dcmspec_explorer" logger's handlers before and after each test."""
    logger = logging.getLogger("dcmspec_explorer")
    logger.handlers = []
    yield
    logger.handlers = []


class TestLoadAppConfigSearchOrder:
    """Tests for load_app_config's env var / user-config-dir / project-dir / cwd priority order."""

    def test_env_var_wins_over_all_other_locations(self, monkeypatch, tmp_path, project_root):
        """The env var config file is picked even when all four locations have a distinguishing file."""
        env_file = tmp_path / "env_config.json"
        _write_json(env_file, {"marker": "env"})
        monkeypatch.setenv("DCMSPEC_EXPLORER_CONFIG", str(env_file))

        _write_json(tmp_path / "config" / "dcmspec_explorer_config.json", {"marker": "user_config_dir"})
        _write_json(project_root / "config" / "dcmspec_explorer_config.json", {"marker": "project_config_dir"})

        _seed_cwd_config(monkeypatch, tmp_path, {"marker": "cwd"})

        config = load_app_config()

        assert config.get_param("marker") == "env"

    def test_user_config_dir_is_picked_when_no_env_var_set(self, monkeypatch, tmp_path):
        """With no env var set, the user-config-dir file (via the patch_dirs patch) is picked."""
        monkeypatch.delenv("DCMSPEC_EXPLORER_CONFIG", raising=False)
        _write_json(tmp_path / "config" / "dcmspec_explorer_config.json", {"marker": "user_config_dir"})

        config = load_app_config()

        assert config.get_param("marker") == "user_config_dir"

    def test_project_config_dir_is_picked_as_fallback(self, monkeypatch, project_root):
        """With no env var and no user-config-dir file, the project's config/ dir file is picked."""
        monkeypatch.delenv("DCMSPEC_EXPLORER_CONFIG", raising=False)
        _write_json(project_root / "config" / "dcmspec_explorer_config.json", {"marker": "project_config_dir"})

        config = load_app_config()

        assert config.get_param("marker") == "project_config_dir"

    def test_cwd_config_is_picked_as_final_fallback(self, monkeypatch, tmp_path, project_root):
        """With no env var, user-config-dir, or project-dir file, the cwd file is picked."""
        monkeypatch.delenv("DCMSPEC_EXPLORER_CONFIG", raising=False)
        _seed_cwd_config(monkeypatch, tmp_path, {"marker": "cwd"})

        config = load_app_config()

        assert config.get_param("marker") == "cwd"


class TestLoadAppConfigDefaults:
    """Tests for load_app_config's default-value handling."""

    def test_missing_log_level_defaults_to_info(self, monkeypatch, tmp_path):
        """A config file with no log_level key gets "INFO" filled in."""
        monkeypatch.delenv("DCMSPEC_EXPLORER_CONFIG", raising=False)
        _write_json(tmp_path / "config" / "dcmspec_explorer_config.json", {})

        config = load_app_config()

        assert config.get_param("log_level") == "INFO"

    def test_missing_show_favorites_on_start_defaults_to_false(self, monkeypatch, tmp_path):
        """A config file with no show_favorites_on_start key gets False filled in."""
        monkeypatch.delenv("DCMSPEC_EXPLORER_CONFIG", raising=False)
        _write_json(tmp_path / "config" / "dcmspec_explorer_config.json", {})

        config = load_app_config()

        assert config.get_param("show_favorites_on_start") is False

    def test_existing_show_favorites_on_start_value_is_not_overwritten(self, monkeypatch, tmp_path):
        """An explicit show_favorites_on_start value in the config file is preserved as-is."""
        monkeypatch.delenv("DCMSPEC_EXPLORER_CONFIG", raising=False)
        _write_json(
            tmp_path / "config" / "dcmspec_explorer_config.json",
            {"show_favorites_on_start": True},
        )

        config = load_app_config()

        assert config.get_param("show_favorites_on_start") is True


class TestSetupLogger:
    """Tests for setup_logger."""

    def test_sets_level_from_config(self, make_config):
        """The logger's level is set from the config's log_level."""
        config = make_config()
        config.set_param("log_level", "DEBUG")

        logger = setup_logger(config)

        assert logger.level == logging.DEBUG

    def test_removes_previous_handlers_so_only_one_survives(self, make_config):
        """Calling setup_logger twice leaves exactly one handler, not a duplicate."""
        config = make_config()
        config.set_param("log_level", "INFO")

        setup_logger(config)
        logger = setup_logger(config)

        assert len(logger.handlers) == 1

    def test_falls_back_to_info_for_invalid_log_level_string(self, make_config):
        """An unrecognized log_level string falls back to INFO rather than raising."""
        config = make_config()
        config.set_param("log_level", "NOT_A_REAL_LEVEL")

        logger = setup_logger(config)

        assert logger.level == logging.INFO
