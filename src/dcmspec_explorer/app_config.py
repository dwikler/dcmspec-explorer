"""Configuration Helper Module for the DCMspec Explorer application."""

import logging
import os
from pathlib import Path

from platformdirs import user_config_dir

from dcmspec.config import Config


def find_project_root(marker="pyproject.toml"):
    """Find the project root by searching for a marker file up the directory tree."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / marker).exists():
            return parent
    raise FileNotFoundError(f"Could not find project root with marker {marker}")


def parse_bool(val):
    """Convert a value to boolean, handling both Python bools and common string representations.

    This is useful for config values that may be stored as either a boolean or a string
    (e.g., true/false, "true"/"false", "yes"/"no", "on"/"off", "1"/"0").

    Args:
        val: The value to convert (bool, str, or any type).

    Returns:
        bool: The converted boolean value.

    """
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)


def load_app_config() -> Config:
    r"""Load app-specific configuration with priority search order.

    Configuration keys:
    - cache_dir (str): Path to the cache directory for downloaded files.
    - log_level (str): Logging level ("DEBUG", "INFO", "WARNING", "ERROR"). Default: "INFO"
    - show_favorites_on_start (bool): If true, start the app in favorites view; otherwise, show all IODs. Default: False

    Search order:
    0. Environment variable (highest priority):
        - Set DCMSPEC_EXPLORER_CONFIG to the full path of a config file to override all other locations.
    1. User config directory (recommended for all users):
        - platformdirs user_config_dir("dcmspec-explorer", "dcmspec"), e.g.:
            - Linux:   ~/.config/dcmspec-explorer/dcmspec_explorer_config.json
            - macOS:   ~/Library/Application Support/dcmspec/dcmspec-explorer/dcmspec_explorer_config.json
            - Windows: %APPDATA%\dcmspec\dcmspec-explorer\dcmspec_explorer_config.json
    2. Project config directory (recommended for developers):
        - config/dcmspec_explorer_config.json in the project root.
    3. Current directory (easy for less experienced users):
        - dcmspec_explorer_config.json in the current working directory.
    4. If no config file is found, or if a key is missing, defaults are used via the base Config class.

    Note: If no config file is found, the Config class will use built-in defaults and a user-writable config directory
    for any files it manages.

    Returns:
        Config: Configuration object with app-specific settings.

    """
    project_root = find_project_root()
    # 0. Environment variable (highest priority)
    env_config = os.environ.get("DCMSPEC_EXPLORER_CONFIG")
    app_config_locations = [
        env_config or None,
        # 1. User config (recommended for all users)
        os.path.join(user_config_dir("dcmspec-explorer", "dcmspec"), "dcmspec_explorer_config.json"),
        # 2. Project config dir (recommended for developers)
        str(project_root / "config" / "dcmspec_explorer_config.json"),
        # 3. Current directory (easy for less experienced users)
        "dcmspec_explorer_config.json",
    ]

    config_file = next(
        (location for location in app_config_locations if location and os.path.exists(location)),
        None,
    )
    config = Config(app_name="dcmspec_explorer", config_file=config_file)

    if config.get_param("log_level") is None:
        config.set_param("log_level", "INFO")

    # Set default for show_favorites_on_start if not specified
    if config.get_param("show_favorites_on_start") is None:
        config.set_param("show_favorites_on_start", False)

    return config


def setup_logger(config: Config) -> logging.Logger:
    """Set up logger with configurable level from config.

    Args:
        config (Config): Configuration object containing log_level setting.

    Returns:
        logging.Logger: Configured logger instance.

    """
    logger = logging.getLogger("dcmspec_explorer")

    # Remove any existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler()

    # Get log level from config
    log_level_str = config.get_param("log_level") or "INFO"
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    logger.setLevel(log_level)
    console_handler.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger
