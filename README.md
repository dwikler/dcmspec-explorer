# DCMspec Explorer (PySide6 Edition)

A modern PySide6-based GUI application for exploring DICOM specifications, powered by the [DCMspec](https://github.com/dwikler/dcmspec) library.

## Features

- Browse and search DICOM IODs
- Download and cache DICOM standard documents
- Creates JSON specification models

## Requirements

- Python 3.8+
- [DCMspec](https://github.com/dwikler/dcmspec)
- PySide6

## Installation

1. **Install Python 3.8+**  
   Download from [python.org](https://www.python.org/downloads/) or use your OS package manager.

2. **(Recommended) Create and activate a virtual environment:**

   On macOS/Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows:

   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install the PySide6 application (dcmspec will be installed automatically as a dependency):**

   ```bash
   git clone https://github.com/dwikler/dcmspec-explorer.git
   cd dcmspec-explorer
   pip install .
   ```

4. **Run the app:**
   ```bash
   dcmspec-explorer
   ```

## Configuration

The application can be configured via a `dcmspec_explorer_config.json` file. Supported keys:

- `cache_dir` (str): Path to the cache directory for downloaded files.
- `log_level` (str): Logging level ("DEBUG", "INFO", "WARNING", "ERROR"). Default: "INFO"
- `show_favorites_on_start` (bool): If true, start the app in favorites view; otherwise, show all IODs. Default: false

### Configuration file search order

When starting, the application looks for a config file in the following order:

1. **Environment variable:**  
   If the `DCMSPEC_EXPLORER_CONFIG` environment variable is set to the full path of a config file, it will be used.

2. **User config directory (recommended for all users):**

   - **Linux:** `~/.config/dcmspec/dcmspec-explorer/dcmspec_explorer_config.json`
   - **macOS:** `~/Library/Application Support/dcmspec/dcmspec-explorer/dcmspec_explorer_config.json`
   - **Windows:** `%APPDATA%\dcmspec\dcmspec-explorer\dcmspec_explorer_config.json`

3. **Project config directory (recommended for developers):**

   - `config/dcmspec_explorer_config.json` in the project root.

4. **Current directory (easy for less experienced users):**
   - `dcmspec_explorer_config.json` in the current working directory.

If no config file is found, built-in defaults are used and all user data is stored in a user-writable config directory.

> **Tip:** You can copy `config/dcmspec_explorer_config.example.json` to any of the above locations and modify it to customize your settings.

### Favorites File Location

The list of your favorite IODs is stored in a file named `favorites.json` in the same directory as your active configuration file.

- If you set the `DCMSPEC_EXPLORER_CONFIG` environment variable, both your config and favorites will be stored in that directory.
- If you use the default user config directory, both files will be there.
- This makes it easy to back up or migrate your settings and favorites together.

> **Tip:** To move your configuration and favorites to another machine, simply copy both your config file and `favorites.json` from the same directory.
