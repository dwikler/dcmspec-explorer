"""Integration tests for the real AppController's View-to-Controller signal wiring.

These tests construct a real AppController (real Model, real MainWindow, real
IODListLoaderServiceMediator/IODModelLoaderServiceMediator), relying on the autouse patch_dirs
fixture (tests/conftest.py) to keep config/cache under pytest's tmp_path.

The module-level autouse prevent_real_background_loads fixture below replaces
start_iodlist_worker/start_iodmodel_worker with no-op fakes for every test in this file. This is
not optional: pytest-qt's per-test teardown pumps the Qt event loop regardless of what a test
itself does, which fires the QTimer.singleShot(0, self.initialize_treeview) scheduled by
AppController.__init__ even for a test that never touches the event loop. Left unpatched, that
starts a real background thread downloading the DICOM standard from the network during teardown,
racing final interpreter shutdown (this was reproduced directly: it segfaults the test process).

Does that mean these tests also need to pump the event loop before asserting on a signal's
effect? No: unlike the deferred QTimer.singleShot above, a signal emitted directly on the main
thread is delivered synchronously under Qt's default AutoConnection, so its effect is already
visible right after the emit() call returns.
"""

import pytest
from anytree import Node
from PySide6.QtCore import QItemSelectionModel

from dcmspec_explorer.controller.app_controller import AppController
from dcmspec_explorer.controller.iod_treeview_adapter import IODTreeViewModelAdapter
from dcmspec_explorer.model.model import IODEntry
from dcmspec_explorer.services.service_mediator import IODListLoaderServiceMediator, IODModelLoaderServiceMediator


def _dummy_content():
    """Return a minimal anytree Module node, just enough to populate one child row."""
    content = Node("content")
    module = Node("PatientModule", parent=content)
    module.module = "Patient"
    module.usage = "Mandatory"
    return content


@pytest.fixture(autouse=True)
def prevent_real_background_loads(monkeypatch):
    """Replace both mediators' worker-starting methods with no-ops for every test in this module."""

    def fake_start_iodlist_worker(self, force_download=False):
        return (None, None)

    def fake_start_iodmodel_worker(self, table_id):
        return (None, None)

    monkeypatch.setattr(IODListLoaderServiceMediator, "start_iodlist_worker", fake_start_iodlist_worker)
    monkeypatch.setattr(IODModelLoaderServiceMediator, "start_iodmodel_worker", fake_start_iodmodel_worker)


class TestCheckForUpdatesClickedWiring:
    """Tests that the Check for Updates button's signal reaches the real IOD list loader mediator."""

    def test_check_for_updates_clicked_starts_iodlist_worker(self, qtbot, monkeypatch):
        """Emitting check_for_updates_clicked calls through to IODListLoaderServiceMediator.start_iodlist_worker."""
        calls = []

        def recording_start_iodlist_worker(self, force_download=False):
            calls.append(force_download)
            return (None, None)

        monkeypatch.setattr(IODListLoaderServiceMediator, "start_iodlist_worker", recording_start_iodlist_worker)
        controller = AppController()
        qtbot.addWidget(controller.view)

        controller.view.check_for_updates_clicked.emit()

        assert calls == [True]


class TestSearchTextChangedWiring:
    """Tests that the search box's signal reaches AppController.apply_filter_and_sort."""

    def test_search_text_changed_triggers_apply_filter_and_sort(self, qtbot, monkeypatch):
        """Typing in the search box calls through to apply_filter_and_sort."""
        controller = AppController()
        qtbot.addWidget(controller.view)
        calls = []
        monkeypatch.setattr(controller, "apply_filter_and_sort", lambda *args, **kwargs: calls.append((args, kwargs)))

        controller.view.ui.searchLineEdit.setText("Alpha")

        assert calls


class TestTreeviewItemSelectedWiring:
    """Tests that a treeview selection reaches AppController and updates the details panel."""

    def test_treeview_item_selected_updates_details_panel(self, qtbot):
        """Selecting a top-level IOD row (with children already loaded) renders its details."""
        controller = AppController()
        qtbot.addWidget(controller.view)
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = controller.treeview_adapter.populate_treeview_model_top_level([entry])
        # Pre-populate a child so the click takes the early-return path in
        # _handle_iod_item_clicked, rather than the not-yet-loaded path that would start a real
        # (here faked, but otherwise real-thread) IOD model load.
        IODTreeViewModelAdapter.populate_treeview_model_item(qt_model.item(0, 0), _dummy_content())
        controller.view.update_treeview(qt_model)
        index = qt_model.indexFromItem(qt_model.item(0, 0))

        controller.view.iod_treeview_item_selected.emit(index)

        assert "Alpha" in controller.view.ui.detailsTextBrowser.toPlainText()


def _select_iod_row(controller, qt_model):
    """Select the treeview's single top-level row, as a user click would."""
    controller.view.update_treeview(qt_model)
    index = qt_model.indexFromItem(qt_model.item(0, 0))
    controller.view.ui.iodTreeView.selectionModel().setCurrentIndex(
        index, QItemSelectionModel.SelectionFlag.ClearAndSelect
    )


class TestToggleFavoriteMenuActionWiring:
    """Tests that the File menu's favorite action reaches the real FavoritesManager."""

    def test_triggering_action_adds_selected_iod_to_favorites(self, qtbot, monkeypatch, tmp_path):
        """Triggering File > favorite action for the selected IOD adds it to favorites.

        Points DCMSPEC_EXPLORER_CONFIG at a tmp_path file so FavoritesManager (which persists
        favorites.json next to the active config file) never touches the real project config/
        directory: the patch_dirs autouse fixture only patches platformdirs' user config
        location, not the "config/ in the project root" fallback that load_app_config falls
        back to when run from the repo root, and this test is the only one in this module whose
        wiring has a real filesystem side effect.
        """
        config_path = tmp_path / "dcmspec_explorer_config.json"
        config_path.write_text("{}")  # must exist on disk: load_app_config skips a missing override path
        monkeypatch.setenv("DCMSPEC_EXPLORER_CONFIG", str(config_path))
        controller = AppController()
        qtbot.addWidget(controller.view)
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = controller.treeview_adapter.populate_treeview_model_top_level([entry])
        _select_iod_row(controller, qt_model)

        controller.view.ui.actionToggleFavorite.trigger()

        assert controller.favorites_manager.is_favorite("table_A.1-1")


class TestFileMenuAboutToShowWiring:
    """Tests that showing the File menu refreshes the Export submenu's and favorite action's state."""

    def test_no_selection_disables_export_submenu_and_favorite_action(self, qtbot):
        """With no IOD selected, opening the File menu disables both Export and the favorite action."""
        controller = AppController()
        qtbot.addWidget(controller.view)

        controller.view.ui.menuFile.aboutToShow.emit()

        assert controller.view.ui.menuExport.isEnabled() is False
        assert controller.view.ui.actionToggleFavorite.isEnabled() is False

    def test_selected_and_loaded_iod_enables_export_submenu(self, qtbot):
        """Once the selected IOD's spec model is loaded, opening the File menu enables Export."""
        controller = AppController()
        qtbot.addWidget(controller.view)
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = controller.treeview_adapter.populate_treeview_model_top_level([entry])
        _select_iod_row(controller, qt_model)
        controller.model.iod_specmodels["table_A.1-1"] = _dummy_content()

        controller.view.ui.menuFile.aboutToShow.emit()

        assert controller.view.ui.menuExport.isEnabled() is True

    def test_selected_iod_enables_favorite_action_with_add_label(self, qtbot):
        """Selecting a non-favorited IOD and opening the File menu enables the action, labeled "Add"."""
        controller = AppController()
        qtbot.addWidget(controller.view)
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = controller.treeview_adapter.populate_treeview_model_top_level([entry])
        _select_iod_row(controller, qt_model)

        controller.view.ui.menuFile.aboutToShow.emit()

        assert controller.view.ui.actionToggleFavorite.isEnabled() is True
        assert controller.view.ui.actionToggleFavorite.text() == "Add to favorites"
