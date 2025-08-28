"""Configuration Helper Module for the DCMspec Explorer application."""

import logging
from pathlib import Path
from dcmspec.config import Config


def find_project_root(marker="pyproject.toml"):
    """Find the project root by searching for a marker file up the directory tree."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / marker).exists():
            return parent
    raise FileNotFoundError(f"Could not find project root with marker {marker}")


def load_app_config() -> Config:
    """Load app-specific configuration with priority search order.

    Configuration keys:
    - cache_dir (str): Path to the cache directory for downloaded files.
    - log_level (str): Logging level ("DEBUG", "INFO", "WARNING", "ERROR"). Default: "INFO"
    - show_favorites_on_start (bool): If true, start the app in favorites view; otherwise, show all IODs. Default: False

    Search order:
    1. App-specific config files (dcmspec_explorer_config.json) - Tier 1
        - Current directory
        - ~/.config/dcmspec-explorer/
        - Project root config directory (config/dcmspec_explorer_config.json)
    2. Base library config file (config.json) - Tier 2 fallback
        - Platform-specific user config directory via Config class
    3. If no config file is found, or if a key is missing, defaults are used.

    Note: The Config class always looks for a config file. When we pass
    config_file=None, it uses user_config_dir(app_name)/config.json as default.

    Returns:
        Config: Configuration object with app-specific settings.

    """
    import os

    project_root = find_project_root()
    app_config_locations = [
        "dcmspec_explorer_config.json",  # Current directory
        os.path.expanduser("~/.config/dcmspec-explorer/dcmspec_explorer_config.json"),  # User config
        str(project_root / "config" / "dcmspec_explorer_config.json"),  # Project root config dir
    ]

    config_file = next(
        (location for location in app_config_locations if os.path.exists(location)),
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
