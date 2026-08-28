# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

DCMspec Explorer is a PySide6 desktop GUI for browsing DICOM IODs (Information Object
Definitions) and their modules/attributes, built on top of the external
[dcmspec](https://github.com/dwikler/dcmspec) library, which handles downloading, caching,
parsing, and building spec models from the DICOM standard (PS3.3) documents.

## Commands

Dependency management is via Poetry.

```bash
poetry install                    # install dependencies
poetry run dcmspec-explorer       # run the application
poetry run compile-ui             # compile Qt Designer .ui files to *_ui.py helpers
poetry run pre-commit install     # set up git pre-commit hooks (one-time)
poetry run pre-commit run --all-files   # run all pre-commit hooks manually
poetry run ruff check --fix --line-length=120 .   # lint
poetry run ruff format --line-length=120 .        # format
poetry run mypy --ignore-missing-imports .        # type check
```

There is no test suite yet (`tests/` only contains `__init__.py`); don't invent test commands.

## Editing Qt Designer `.ui` files

UI is designed in Qt Designer (`.ui` files under `src/dcmspec_explorer/resources/`) and compiled
to Python via `pyside6-uic`, **not** loaded at runtime. After editing a `.ui` file:

1. Run `poetry run compile-ui` to regenerate the corresponding `*_ui.py` file in `src/dcmspec_explorer/view/`.
2. Test the app to confirm the UI changes work.
3. Commit both the `.ui` file and its regenerated `*_ui.py` helper together — they must stay in sync.

The `compile-ui` pre-commit hook regenerates these automatically on commit if `.ui` files changed,
but if it modifies files you'll need to re-stage and re-commit. Never hand-edit a `*_ui.py` file;
generated view files are excluded from ruff linting (`tool.ruff.exclude` in `pyproject.toml`).

## Architecture

The app follows an MVP (Model-View-Presenter) pattern, with `AppController` acting as the
Presenter (named "Controller" for familiarity — see the docstring in `app_controller.py`).

- **`main.py`** creates the `QApplication` and a single `AppController`, which owns and wires
  together the `Model` and `MainWindow` (View).
- **`model/model.py`** (`Model`) loads and caches two things via the `dcmspec` library:
  - the IOD list, scraped from the DICOM PS3.3 "list of tables" HTML page
    (`XHTMLDocHandler`, `DOMTableSpecParser`), tracked as `IODEntry` namedtuples.
  - individual IOD spec models (module/attribute trees), built on demand per `table_id` via
    `IODSpecBuilder`/`SpecFactory` and cached in memory (`_iod_specmodels`) and on disk as JSON.
  It also owns DICOM-version-aware cache archiving: when a reload detects a new DICOM standard
  version, the previous `cache/standard` and `cache/model` folders are moved into a
  `cache/<version>/` archive before the new data is written.
- **`view/main_window.py`** (`MainWindow`) wraps the generated `main_window_ui.py`. It contains
  no business logic — it only exposes Qt signals (e.g. `iod_treeview_item_selected`,
  `search_text_changed`, `reload_clicked`) for user actions and public setter methods
  (`set_details_html`, `update_treeview`, `show_error`, ...) for the controller to update it.
- **`controller/app_controller.py`** (`AppController`) connects the view's signals to handlers,
  calls into `Model`, and pushes results back to the view. It also owns filtering/sorting state
  (`apply_filter_and_sort`) and favorites toggling.
- **`controller/iod_treeview_adapter.py`** (`IODTreeViewModelAdapter`) converts `IODEntry` lists
  and `dcmspec` `SpecModel`/`anytree` `Node` trees into a `QStandardItemModel` for the treeview,
  attaching lookup data via custom Qt item-data roles defined in `qt/qt_roles.py`
  (`TABLE_ID_ROLE`, `TABLE_URL_ROLE`, `NODE_PATH_ROLE`, `IS_FAVORITE_ROLE`).
- **`services/`** implements background loading so the UI thread never blocks:
  - `iod_loading_service.py` defines plain worker classes (`IODListLoaderWorker`,
    `IODModelLoaderWorker`) that run in a `threading.Thread` and push `(event_type, data)` tuples
    (`"progress"`, `"loaded"`, `"error"`) onto a `queue.Queue`.
  - `service_mediator.py` (`BaseServiceMediator` and its subclasses) starts the worker thread,
    polls the queue with a `QTimer` (every 50ms) on the main thread, and re-emits events as Qt
    signals with `Qt.QueuedConnection`. This queue+poll+signal bridge is the standard pattern for
    getting background work back onto the Qt main thread safely — follow it for any new
    long-running operation rather than touching Qt widgets from a worker thread directly.
  - `favorites_manager.py` (`FavoritesManager`) persists favorite `table_id`s to `favorites.json`
    next to the active config file, using a write-to-temp-then-`os.replace` pattern.
- **`app_config.py`** loads app config via `dcmspec.config.Config` with a priority search order:
  `DCMSPEC_EXPLORER_CONFIG` env var → user config dir (via `platformdirs`) → `config/` in the
  project root → current working directory. See README.md for the full details and supported keys
  (`cache_dir`, `log_level`, `show_favorites_on_start`).

## Notes

- `scratch/` is a gitignored scratch space for local experiments; don't treat its contents as
  part of the shipped codebase.
- Ruff config lives in `pyproject.toml` (`line-length = 120`, rule sets `E`, `F`, `D`, with `D203`
  and `D213` ignored in favor of `D211`/`D212`).
