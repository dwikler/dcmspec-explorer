"""Unit tests for dcmspec_explorer.controller.app_controller.AppController.

These tests are QApplication-independent, not Qt-independent. They freely use real, lightweight
PySide6 QtCore/QtGui objects (QStandardItem, QStandardItemModel via the real
IODTreeViewModelAdapter, QModelIndex, QUrl), which are verified to work without a live
QApplication — but none of them construct a QApplication, run an event loop, or touch a real
QtWidgets widget. The two branches that do construct a real widget (QMenu, LoadIODDialog) are
only reachable via a per-test monkeypatch of those names at the app_controller module level.

They are handler-level tests built on the unbound-method + SimpleNamespace test pattern (see
make_controller_state below): rather than constructing a real AppController (which would require
a real QApplication, Model, MainWindow, and live Qt signal wiring), each test calls one
AppController method directly against a plain types.SimpleNamespace standing in for `self`. Real
AppController instance methods are bound onto that namespace via functools.partial, so internal
`self.<method>(...)` calls made by the handler under test (e.g. _on_check_for_updates_clicked calling
self._connect_iodlist_signals) resolve to the real implementation, operating on fake view/model/
service collaborators. This exercises real, interconnected controller logic and lets tests assert
on its effects (what the fake view/model/service recorded) rather than on implementation details.

The real IODTreeViewModelAdapter is used as treeview_adapter throughout: its own correctness is
already pinned down in tests/unit/test_iod_treeview_adapter.py.
"""

import functools
import logging
import types

import pytest
from anytree import Node
from PySide6.QtCore import QModelIndex, QUrl
from PySide6.QtGui import QStandardItem

from dcmspec.progress import Progress, ProgressStatus

import dcmspec_explorer.controller.app_controller as app_controller_module
from dcmspec_explorer.controller.app_controller import AppController
from dcmspec_explorer.controller.iod_treeview_adapter import IODTreeViewModelAdapter
from dcmspec_explorer.model.model import IODEntry
from dcmspec_explorer.qt.qt_roles import TABLE_ID_ROLE, NODE_PATH_ROLE


# AppController instance methods that internally call other self.<method>(...) helpers (or are
# themselves such helpers). Bound onto the fake self by make_controller_state so those internal
# calls resolve to the real implementation. Excludes __init__ (whose side effects this pattern is
# built to bypass) and run (a thin self.view.show() wrapper, not exercised at this layer).
_BOUND_METHOD_NAMES = [
    "initialize_treeview",
    "_on_search_text_changed",
    "_on_toggle_favorite_display_clicked",
    "_on_treeview_item_clicked",
    "get_selected_item_details",
    "_on_treeview_right_click",
    "_favorite_action_label",
    "_is_iod_loaded",
    "_export_selected_iod",
    "_on_toggle_favorite_state_action_triggered",
    "_on_file_menu_about_to_show",
    "_export_iod_model",
    "_connect_export_signals",
    "_handle_export_loaded",
    "_handle_export_error",
    "_report_error",
    "_on_check_for_updates_clicked",
    "_toggle_favorite",
    "_safe_disconnect",
    "_connect_signals",
    "_connect_iodlist_signals",
    "_handle_iod_item_clicked",
    "_handle_module_item_clicked",
    "_handle_attribute_item_clicked",
    "_handle_iodlist_progress",
    "_handle_iodlist_loaded",
    "_handle_iodlist_error",
    "_handle_iodmodel_progress",
    "_handle_iodmodel_loaded",
    "_handle_iodmodel_error",
    "_on_details_link_clicked",
    "apply_filter_and_sort",
    "_on_treeview_header_clicked",
]


def make_controller_state(view, model, logger, favorites_manager=None, **overrides):
    """Build a fake AppController `self` for the unbound-method + SimpleNamespace test pattern."""
    fake_self = types.SimpleNamespace(
        view=view,
        model=model,
        favorites_manager=favorites_manager,
        treeview_adapter=IODTreeViewModelAdapter(favorites_manager=favorites_manager),
        service=FakeMediator(),
        iod_model_service=FakeMediator(),
        export_service=FakeMediator(),
        logger=logger,
        sort_column=None,
        sort_reverse=False,
        show_favorites_only=False,
        progress_dialog=None,
        _normalize_export_filename=AppController._normalize_export_filename,
    )
    for name in _BOUND_METHOD_NAMES:
        setattr(fake_self, name, functools.partial(getattr(AppController, name), fake_self))
    for key, value in overrides.items():
        setattr(fake_self, key, value)
    return fake_self


class HostileSpecModelsDict(dict):
    """Dict that injects a new key into itself right after its first items() entry is yielded.

    Mutating a dict while a live iterator over it exists raises RuntimeError in CPython. This
    reproduces that deterministically, standing in for the real hazard of Model._iod_specmodels
    being mutated by a concurrent load/reload while _handle_iodlist_loaded is iterating it,
    without needing an actual racing background thread.
    """

    def items(self):
        """Yield each item, injecting a new key into self right after the first is yielded."""
        iterator = dict.items(self)
        for index, item in enumerate(iterator):
            if index == 0:
                self["injected_during_iteration"] = item[1]
            yield item


class FakeIodModel:
    """Fake loaded IOD spec model exposing only the .content attribute the controller reads."""

    def __init__(self, content):
        """Initialize with the given anytree content root."""
        self.content = content


class FakeModel:
    """Fake data model exposing the subset of Model's surface AppController reads/calls."""

    def __init__(
        self,
        iod_list=None,
        iod_specmodels=None,
        version=None,
        new_version_available=False,
        node_attrs=None,
        module_ref_link="",
        cached_table_ids=None,
    ):
        """Initialize with canned values for each Model property/method the controller uses."""
        self.iod_list = iod_list if iod_list is not None else []
        self.iod_specmodels = iod_specmodels if iod_specmodels is not None else {}
        self.version = version
        self.new_version_available = new_version_available
        self._node_attrs = node_attrs or {}
        self._module_ref_link = module_ref_link
        self._cached_table_ids = set(cached_table_ids or [])

    def get_node_public_attrs(self, table_id, relative_path):
        """Return the canned details dict for (table_id, relative_path), or None if unset."""
        return self._node_attrs.get((table_id, relative_path))

    def get_module_ref_link(self, ref_html):
        """Return the canned formatted reference link, ignoring the input."""
        return self._module_ref_link

    def is_iod_model_cached(self, table_id):
        """Return whether table_id is in the cached table_ids set."""
        return table_id in self._cached_table_ids


class FakeFavoritesManager:
    """Fake favorites manager backed by a plain set, optionally raising on add/remove."""

    def __init__(self, favorite_table_ids=None, raise_on_add=None, raise_on_remove=None):
        """Initialize with the given favorite table_ids and optional canned exceptions."""
        self._favorites = set(favorite_table_ids or [])
        self._raise_on_add = raise_on_add
        self._raise_on_remove = raise_on_remove
        self.add_calls = []
        self.remove_calls = []

    def is_favorite(self, table_id):
        """Return whether table_id is in the favorites set."""
        return table_id in self._favorites

    def add_favorite(self, table_id):
        """Record the call, then add table_id or raise the canned exception."""
        self.add_calls.append(table_id)
        if self._raise_on_add:
            raise self._raise_on_add
        self._favorites.add(table_id)

    def remove_favorite(self, table_id):
        """Record the call, then remove table_id or raise the canned exception."""
        self.remove_calls.append(table_id)
        if self._raise_on_remove:
            raise self._raise_on_remove
        self._favorites.discard(table_id)

    def filter_iod_entry_list(self, iod_entry_list):
        """Return only the entries whose table_id is a favorite."""
        return [iod for iod in iod_entry_list if iod.table_id in self._favorites]


class FakeSignal:
    """Fake Qt signal recording connect/disconnect calls, standing in for mediator signals."""

    def __init__(self):
        """Initialize with no connected slots."""
        self.connected = []

    def connect(self, slot, *args, **kwargs):
        """Record the connected slot."""
        self.connected.append(slot)

    def disconnect(self, *args, **kwargs):
        """Clear all connected slots."""
        self.connected = []


class FakeMediator:
    """Fake service mediator standing in for service, iod_model_service, or export_service.

    Exposes the iodlist_*, iodmodel_*, and iodexport_* signal attributes so a single instance can
    stand in for AppController.service (IODListLoaderServiceMediator), AppController.iod_model_service
    (IODModelLoaderServiceMediator), or AppController.export_service (IODExportServiceMediator), as
    make_controller_state below uses it for all three.
    """

    def __init__(self):
        """Initialize all eight signal attributes and empty call-recording lists."""
        self.iodlist_progress_signal = FakeSignal()
        self.iodlist_loaded_signal = FakeSignal()
        self.iodlist_error_signal = FakeSignal()
        self.iodmodel_progress_signal = FakeSignal()
        self.iodmodel_loaded_signal = FakeSignal()
        self.iodmodel_error_signal = FakeSignal()
        self.iodexport_loaded_signal = FakeSignal()
        self.iodexport_error_signal = FakeSignal()
        self.start_iodlist_worker_calls = []
        self.start_iodmodel_worker_calls = []
        self.start_export_worker_calls = []

    def start_iodlist_worker(self, force_download=False):
        """Record the call and return a dummy (worker, thread) pair."""
        self.start_iodlist_worker_calls.append(force_download)
        return ("fake_worker", "fake_thread")

    def start_iodmodel_worker(self, table_id):
        """Record the call and return a dummy (worker, thread) pair."""
        self.start_iodmodel_worker_calls.append(table_id)
        return ("fake_worker", "fake_thread")

    def start_export_worker(self, iod_model, fmt, output_path):
        """Record the call and return a dummy (worker, thread) pair."""
        self.start_export_worker_calls.append((iod_model, fmt, output_path))
        return ("fake_worker", "fake_thread")


class FakeSelectionModel:
    """Fake QItemSelectionModel exposing only hasSelection/currentIndex."""

    def __init__(self, current_index=None):
        """Initialize with the given current QModelIndex, or None for no selection."""
        self._current_index = current_index

    def hasSelection(self):
        """Return whether a current index was configured."""
        return self._current_index is not None

    def currentIndex(self):
        """Return the configured current index."""
        return self._current_index


class FakeTreeViewHeader:
    """Fake treeview header exposing only setSortIndicatorShown."""

    def __init__(self):
        """Initialize with an empty call-recording list."""
        self.sort_indicator_shown_calls = []

    def setSortIndicatorShown(self, shown):
        """Record the call."""
        self.sort_indicator_shown_calls.append(shown)


class FakeIodTreeView:
    """Fake iodTreeView widget mirroring the specific methods AppController reaches into.

    Its setModel/model pair is wired the same way MainWindow.update_treeview wires the real
    widget, so that a handler reading back self.view.ui.iodTreeView.model() after
    self.view.update_treeview(...) sees the model that was just set, without needing a real Qt
    widget or QApplication.
    """

    def __init__(self, model=None, selection_model=None):
        """Initialize with an optional starting model and selection model."""
        self._model = model
        self._selection_model = selection_model if selection_model is not None else FakeSelectionModel()
        self._header = FakeTreeViewHeader()
        self.set_enabled_calls = []
        self.expand_calls = []
        self.set_current_index_calls = []

    def setEnabled(self, enabled):
        """Record the call."""
        self.set_enabled_calls.append(enabled)

    def setModel(self, model):
        """Store the given model, as the real widget does for later model() calls."""
        self._model = model

    def model(self):
        """Return the currently set model."""
        return self._model

    def selectionModel(self):
        """Return the configured selection model."""
        return self._selection_model

    def setCurrentIndex(self, index):
        """Record the call."""
        self.set_current_index_calls.append(index)

    def expand(self, index):
        """Record the call."""
        self.expand_calls.append(index)

    def header(self):
        """Return the fake header."""
        return self._header


class FakeSearchLineEdit:
    """Fake search box exposing only text()."""

    def __init__(self, text=""):
        """Initialize with the given search text."""
        self._text = text

    def text(self):
        """Return the configured search text."""
        return self._text


class FakeVersionLabel:
    """Fake version label exposing only setText."""

    def __init__(self):
        """Initialize with an empty call-recording list."""
        self.set_text_calls = []

    def setText(self, text):
        """Record the call."""
        self.set_text_calls.append(text)


class FakeUi:
    """Fake `.ui` namespace mirroring the specific widget reach-ins AppController performs."""

    def __init__(self, iod_tree_view=None, search_text=""):
        """Initialize the iodTreeView, searchLineEdit, and versionLabel fakes."""
        self.iodTreeView = iod_tree_view if iod_tree_view is not None else FakeIodTreeView()
        self.searchLineEdit = FakeSearchLineEdit(search_text)
        self.versionLabel = FakeVersionLabel()


class FakeView:
    """Fake View mirroring MainWindow's documented setter contract, plus the `.ui` reach-ins."""

    def __init__(self, ui=None, save_file_return=None, selected_iod=None):
        """Initialize the `.ui` namespace and empty call-recording lists for every setter.

        Args:
            ui: Optional FakeUi override.
            save_file_return: Canned return value for prompt_save_file (None simulates Cancel).
            selected_iod: Canned (table_id, name) tuple returned by get_selected_iod, or None.

        """
        self.ui = ui if ui is not None else FakeUi()
        self.details_html_calls = []
        self.nodetails_html_calls = []
        self.error_calls = []
        self.info_calls = []
        self.status_bar_calls = []
        self.update_treeview_calls = []
        self.sort_indicator_calls = []
        self.favorites_button_label_calls = []
        self.anchor_warning_calls = []
        self.url_warning_calls = []
        self.prompt_save_file_calls = []
        self._save_file_return = save_file_return
        self._selected_iod = selected_iod
        self.export_menu_enabled_calls = []
        self.favorite_action_calls = []

    def set_details_html(self, html_body):
        """Record the call."""
        self.details_html_calls.append(html_body)

    def set_nodetails_html(self, selected_item_name, kind):
        """Record the call."""
        self.nodetails_html_calls.append((selected_item_name, kind))

    def show_error(self, message):
        """Record the call."""
        self.error_calls.append(message)

    def show_info(self, title, message):
        """Record the call."""
        self.info_calls.append((title, message))

    def update_status_bar(self, message):
        """Record the call."""
        self.status_bar_calls.append(message)

    def update_treeview(self, tree_model):
        """Record the call and push the model onto the fake iodTreeView, as MainWindow does."""
        self.update_treeview_calls.append(tree_model)
        self.ui.iodTreeView.setModel(tree_model)

    def update_treeview_sort_indicator(self, sort_column, sort_reverse):
        """Record the call."""
        self.sort_indicator_calls.append((sort_column, sort_reverse))

    def prompt_save_file(self, title, default_name, file_filter):
        """Record the call and return the configured canned path (or None for Cancel)."""
        self.prompt_save_file_calls.append((title, default_name, file_filter))
        return self._save_file_return

    def set_show_favorites_button_label(self, show_favorites):
        """Record the call."""
        self.favorites_button_label_calls.append(show_favorites)

    def show_anchor_link_warning_dialog(self, url_str):
        """Record the call."""
        self.anchor_warning_calls.append(url_str)

    def show_url_link_warning_dialog(self, url_str):
        """Record the call."""
        self.url_warning_calls.append(url_str)

    def get_selected_iod(self):
        """Return the canned (table_id, name) selection configured at construction time."""
        return self._selected_iod

    def set_export_menu_enabled(self, enabled, disabled_tooltip=""):
        """Record the call."""
        self.export_menu_enabled_calls.append((enabled, disabled_tooltip))

    def set_favorite_action(self, enabled, is_favorite):
        """Record the call."""
        self.favorite_action_calls.append((enabled, is_favorite))


class FakeQAction:
    """Fake QAction exposing a fake `triggered` signal."""

    def __init__(self, text):
        """Initialize with the given action text."""
        self.text = text
        self.triggered = FakeSignal()


class FakeQMenu:
    """Fake QMenu recording added actions/submenus and exec() calls, for the monkeypatched QMenu tests."""

    instances: list["FakeQMenu"] = []

    def __init__(self, parent=None, title="", _register=True):
        """Initialize and, for a top-level menu, register self in the class-level instances list.

        Submenus (created via addMenu) pass _register=False so they don't also land in
        `instances` — only the top-level QMenu(self.view) construction the controller performs
        should be found there, matching the pre-submenu test contract of `instances[-1]`.
        """
        self.parent = parent
        self.title = title
        self.actions = []
        self.submenus = {}
        self.exec_calls = []
        self.enabled = True
        self.tool_tip = ""
        if _register:
            FakeQMenu.instances.append(self)

    def addAction(self, text):
        """Record and return a new FakeQAction."""
        action = FakeQAction(text)
        self.actions.append(action)
        return action

    def addMenu(self, title):
        """Record and return a new FakeQMenu standing in for a submenu, keyed by title."""
        submenu = FakeQMenu(parent=self, title=title, _register=False)
        self.submenus[title] = submenu
        return submenu

    def setEnabled(self, enabled):
        """Record the call."""
        self.enabled = enabled

    def menuAction(self):
        """Return self, standing in for the QAction representing this submenu in its parent menu."""
        return self

    def setToolTip(self, tool_tip):
        """Record the call."""
        self.tool_tip = tool_tip

    def exec(self, pos):
        """Record the call."""
        self.exec_calls.append(pos)


class FakeLoadIODDialog:
    """Fake LoadIODDialog recording show/accept/reject/update_step calls."""

    instances: list["FakeLoadIODDialog"] = []

    def __init__(self, parent=None):
        """Initialize and register self in the class-level instances list."""
        self.parent = parent
        self.shown = False
        self.accepted = False
        self.rejected = False
        self.update_step_calls = []
        FakeLoadIODDialog.instances.append(self)

    def show(self):
        """Record the call."""
        self.shown = True

    def accept(self):
        """Record the call."""
        self.accepted = True

    def reject(self):
        """Record the call."""
        self.rejected = True

    def update_step(self, status, percent):
        """Record the call."""
        self.update_step_calls.append((status, percent))


def _iod_index_with_children(children_populated):
    """Return (qt_model, index, name_item, kind_item) for a single top-level IOD row.

    children_populated=True gives it one already-populated Module child; False leaves it empty.
    """
    entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
    adapter = IODTreeViewModelAdapter()
    qt_model = adapter.populate_treeview_model_top_level([entry])
    iod_item = qt_model.item(0, 0)
    if children_populated:
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"
        IODTreeViewModelAdapter.populate_treeview_model_item(iod_item, content)
    index = qt_model.indexFromItem(iod_item)
    name_item = qt_model.itemFromIndex(index.siblingAtColumn(0))
    kind_item = qt_model.itemFromIndex(index.siblingAtColumn(1))
    return qt_model, index, name_item, kind_item


def _build_iod_tree_with_module_and_attribute():
    """Return (qt_model, iod_index, module_index, attribute_index) for a 3-level IOD tree."""
    entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
    adapter = IODTreeViewModelAdapter()
    qt_model = adapter.populate_treeview_model_top_level([entry])
    iod_item = qt_model.item(0, 0)

    content = Node("content")
    module = Node("PatientModule", parent=content)
    module.module = "Patient"
    module.usage = "Mandatory"
    attribute = Node("PatientNameAttr", parent=module)
    attribute.elem_name = "PatientName"
    attribute.elem_tag = "(0010,0010)"
    attribute.elem_type = "1"

    IODTreeViewModelAdapter.populate_treeview_model_item(iod_item, content)
    module_item = iod_item.child(0, 0)
    attribute_item = module_item.child(0, 0)

    iod_index = qt_model.indexFromItem(iod_item)
    module_index = qt_model.indexFromItem(module_item)
    attribute_index = qt_model.indexFromItem(attribute_item)
    return qt_model, iod_index, module_index, attribute_index


class TestInitializeTreeview:
    """Tests for AppController.initialize_treeview."""

    def test_starts_iodlist_worker_without_force_and_updates_status_bar(self, fake_logger):
        """The initial load starts the worker with the default force_download=False."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state.initialize_treeview()

        assert state.service.start_iodlist_worker_calls == [False]
        assert view.status_bar_calls[-1] == "Loading IOD modules..."


class TestOnCheckForUpdatesClicked:
    """Tests for AppController._on_check_for_updates_clicked."""

    def test_starts_iodlist_worker_with_force_download_and_updates_status_bar(self, fake_logger):
        """The Check for Updates button forces a fresh download and shows a downloading message."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._on_check_for_updates_clicked()

        assert state.service.start_iodlist_worker_calls == [True]
        assert view.status_bar_calls[-1] == "Downloading latest IOD modules from web..."
        assert state.service.iodlist_loaded_signal.connected


class TestOnSearchTextChanged:
    """Tests for AppController._on_search_text_changed."""

    def test_delegates_to_apply_filter_and_sort(self, fake_logger):
        """A search text change rebuilds the treeview filtered by the (now current) search text."""
        entries = [
            IODEntry("Alpha", "table_A.1-1", "url", "Composite"),
            IODEntry("Beta", "table_B.1-1", "url2", "Composite"),
        ]
        model = FakeModel(iod_list=entries)
        view = FakeView(ui=FakeUi(search_text="Alpha"))
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state._on_search_text_changed("Alpha")

        assert view.update_treeview_calls[-1].rowCount() == 1


class TestOnToggleFavoritesClicked:
    """Tests for AppController._on_toggle_favorite_display_clicked."""

    def test_toggles_flag_updates_button_label_and_delegates(self, fake_logger):
        """Each click flips show_favorites_only, relabels the button, and rebuilds the treeview."""
        view = FakeView()
        state = make_controller_state(
            view=view, model=FakeModel(), logger=fake_logger, favorites_manager=FakeFavoritesManager()
        )

        state._on_toggle_favorite_display_clicked()
        assert state.show_favorites_only is True
        assert view.favorites_button_label_calls == [True]
        assert view.update_treeview_calls

        state._on_toggle_favorite_display_clicked()
        assert state.show_favorites_only is False
        assert view.favorites_button_label_calls == [True, False]


class TestOnTreeviewHeaderClicked:
    """Tests for AppController._on_treeview_header_clicked."""

    def test_non_sortable_column_hides_indicator_and_leaves_sort_state_untouched(self, fake_logger):
        """Clicking the Usage column (index 2) is a no-op besides hiding the sort indicator."""
        view = FakeView()
        state = make_controller_state(
            view=view, model=FakeModel(), logger=fake_logger, sort_column=1, sort_reverse=True
        )

        state._on_treeview_header_clicked(2)

        assert view.ui.iodTreeView.header().sort_indicator_shown_calls == [False]
        assert state.sort_column == 1
        assert state.sort_reverse is True
        assert view.sort_indicator_calls == []

    def test_clicking_same_sortable_column_toggles_reverse(self, fake_logger):
        """Re-clicking the currently sorted column flips sort_reverse."""
        view = FakeView()
        state = make_controller_state(
            view=view, model=FakeModel(), logger=fake_logger, sort_column=0, sort_reverse=False
        )

        state._on_treeview_header_clicked(0)

        assert state.sort_column == 0
        assert state.sort_reverse is True
        assert view.sort_indicator_calls[-1] == (0, True)

    def test_clicking_new_sortable_column_sets_it_ascending(self, fake_logger):
        """Clicking a different sortable column switches to it, ascending."""
        view = FakeView()
        state = make_controller_state(
            view=view, model=FakeModel(), logger=fake_logger, sort_column=0, sort_reverse=True
        )

        state._on_treeview_header_clicked(1)

        assert state.sort_column == 1
        assert state.sort_reverse is False


class TestApplyFilterAndSort:
    """Tests for AppController.apply_filter_and_sort."""

    def test_uses_model_iod_list_when_no_explicit_list_given(self, fake_logger):
        """With no iod_entry_list argument, the model's own iod_list is used."""
        entries = [IODEntry("Alpha", "table_A.1-1", "url", "Composite")]
        model = FakeModel(iod_list=entries)
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state.apply_filter_and_sort()

        assert view.update_treeview_calls[-1].rowCount() == 1

    def test_uses_explicit_list_when_given(self, fake_logger):
        """An explicit iod_entry_list overrides the model's iod_list."""
        model = FakeModel(iod_list=[IODEntry("Alpha", "table_A.1-1", "url", "Composite")])
        explicit_entries = [
            IODEntry("Beta", "table_B.1-1", "url2", "Composite"),
            IODEntry("Gamma", "table_G.1-1", "url3", "Composite"),
        ]
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state.apply_filter_and_sort(iod_entry_list=explicit_entries)

        assert view.update_treeview_calls[-1].rowCount() == 2

    def test_applies_favorites_filter_when_show_favorites_only(self, fake_logger):
        """With show_favorites_only, only favorited entries are displayed."""
        entries = [
            IODEntry("Alpha", "table_A.1-1", "url", "Composite"),
            IODEntry("Beta", "table_B.1-1", "url2", "Composite"),
        ]
        model = FakeModel(iod_list=entries)
        favorites = FakeFavoritesManager(favorite_table_ids={"table_B.1-1"})
        view = FakeView()
        state = make_controller_state(
            view=view, model=model, logger=fake_logger, favorites_manager=favorites, show_favorites_only=True
        )

        state.apply_filter_and_sort()

        qt_model = view.update_treeview_calls[-1]
        assert qt_model.rowCount() == 1
        assert qt_model.item(0, 0).text() == "Beta"

    def test_restores_selection_by_table_id_when_still_present(self, fake_logger):
        """A previously selected table_id still present after rebuild gets reselected."""
        entries = [
            IODEntry("Alpha", "table_A.1-1", "url", "Composite"),
            IODEntry("Beta", "table_B.1-1", "url2", "Composite"),
        ]
        model = FakeModel(iod_list=entries)
        prior_model = IODTreeViewModelAdapter().populate_treeview_model_top_level(entries)
        selected_index = prior_model.indexFromItem(prior_model.item(1, 0))
        iod_tree_view = FakeIodTreeView(selection_model=FakeSelectionModel(current_index=selected_index))
        view = FakeView(ui=FakeUi(iod_tree_view=iod_tree_view))
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state.apply_filter_and_sort()

        assert view.ui.iodTreeView.set_current_index_calls
        restored_index = view.ui.iodTreeView.set_current_index_calls[-1]
        new_model = view.update_treeview_calls[-1]
        assert new_model.itemFromIndex(restored_index).data(TABLE_ID_ROLE) == "table_B.1-1"

    def test_does_not_restore_selection_when_filtered_out(self, fake_logger):
        """A previously selected table_id excluded by the current search text is not reselected."""
        entries = [
            IODEntry("Alpha", "table_A.1-1", "url", "Composite"),
            IODEntry("Beta", "table_B.1-1", "url2", "Composite"),
        ]
        model = FakeModel(iod_list=entries)
        prior_model = IODTreeViewModelAdapter().populate_treeview_model_top_level(entries)
        selected_index = prior_model.indexFromItem(prior_model.item(1, 0))
        iod_tree_view = FakeIodTreeView(selection_model=FakeSelectionModel(current_index=selected_index))
        view = FakeView(ui=FakeUi(iod_tree_view=iod_tree_view, search_text="Alpha"))
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state.apply_filter_and_sort()

        assert view.ui.iodTreeView.set_current_index_calls == []


class TestGetSelectedItemDetails:
    """Tests for AppController.get_selected_item_details."""

    def test_returns_none_when_item_has_no_table_id_in_ancestry(self, fake_logger):
        """An item with no TABLE_ID_ROLE anywhere in its ancestry short-circuits to None."""
        item = QStandardItem()
        state = make_controller_state(view=FakeView(), model=FakeModel(), logger=fake_logger)

        assert state.get_selected_item_details(item) is None

    def test_strips_leading_content_segment_from_node_path(self, fake_logger):
        """A NODE_PATH_ROLE starting with "content/" has that segment stripped before lookup."""
        item = QStandardItem()
        item.setData("table_A.1-1", TABLE_ID_ROLE)
        item.setData("content/PatientModule", NODE_PATH_ROLE)
        model = FakeModel(node_attrs={("table_A.1-1", "PatientModule"): {"module": "Patient"}})
        state = make_controller_state(view=FakeView(), model=model, logger=fake_logger)

        assert state.get_selected_item_details(item) == {"module": "Patient"}

    def test_uses_full_path_when_no_leading_content_segment(self, fake_logger):
        """A NODE_PATH_ROLE without a leading "content" segment is used unmodified."""
        item = QStandardItem()
        item.setData("table_A.1-1", TABLE_ID_ROLE)
        item.setData("PatientModule", NODE_PATH_ROLE)
        model = FakeModel(node_attrs={("table_A.1-1", "PatientModule"): {"module": "Patient"}})
        state = make_controller_state(view=FakeView(), model=model, logger=fake_logger)

        assert state.get_selected_item_details(item) == {"module": "Patient"}


class TestOnTreeviewItemClicked:
    """Tests for AppController._on_treeview_item_clicked's level-based dispatch."""

    def test_invalid_model_returns_early(self, fake_logger):
        """An index with no model (e.g. QModelIndex()) is ignored."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._on_treeview_item_clicked(QModelIndex())

        assert view.details_html_calls == []

    def test_top_level_click_dispatches_to_iod_item_handler(self, fake_logger):
        """A top-level (IOD) click renders the IOD details html."""
        qt_model, iod_index, _module_index, _attribute_index = _build_iod_tree_with_module_and_attribute()
        view = FakeView(ui=FakeUi(iod_tree_view=FakeIodTreeView(model=qt_model)))
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._on_treeview_item_clicked(iod_index)

        assert "Alpha IOD" in view.details_html_calls[-1]

    def test_module_level_click_with_details_dispatches_to_module_handler(self, fake_logger):
        """A second-level (Module) click with a resolvable node renders the module details html."""
        qt_model, _iod_index, module_index, _attribute_index = _build_iod_tree_with_module_and_attribute()
        view = FakeView(ui=FakeUi(iod_tree_view=FakeIodTreeView(model=qt_model)))
        model = FakeModel(
            node_attrs={
                ("table_A.1-1", "PatientModule"): {
                    "module": "Patient",
                    "ie": "Patient",
                    "usage": "M",
                    "ref": "",
                    "description": "",
                }
            }
        )
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state._on_treeview_item_clicked(module_index)

        assert "Patient Module" in view.details_html_calls[-1]
        assert view.nodetails_html_calls == []

    def test_module_level_click_without_details_shows_nodetails(self, fake_logger):
        """A Module click with no matching node falls back to the "no details" message."""
        qt_model, _iod_index, module_index, _attribute_index = _build_iod_tree_with_module_and_attribute()
        view = FakeView(ui=FakeUi(iod_tree_view=FakeIodTreeView(model=qt_model)))
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._on_treeview_item_clicked(module_index)

        assert view.nodetails_html_calls[-1][1] == "Module"

    def test_attribute_level_click_with_details_dispatches_to_attribute_handler(self, fake_logger):
        """A third-level (Attribute) click with a resolvable node renders the attribute details html."""
        qt_model, _iod_index, _module_index, attribute_index = _build_iod_tree_with_module_and_attribute()
        view = FakeView(ui=FakeUi(iod_tree_view=FakeIodTreeView(model=qt_model)))
        model = FakeModel(
            node_attrs={
                ("table_A.1-1", "PatientModule/PatientNameAttr"): {
                    "elem_name": "PatientName",
                    "elem_tag": "(0010,0010)",
                    "elem_type": "1",
                    "elem_description": "",
                }
            }
        )
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state._on_treeview_item_clicked(attribute_index)

        assert "PatientName Attribute" in view.details_html_calls[-1]

    def test_attribute_level_click_without_details_shows_nodetails(self, fake_logger):
        """An Attribute click with no matching node falls back to the "no details" message."""
        qt_model, _iod_index, _module_index, attribute_index = _build_iod_tree_with_module_and_attribute()
        view = FakeView(ui=FakeUi(iod_tree_view=FakeIodTreeView(model=qt_model)))
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._on_treeview_item_clicked(attribute_index)

        assert view.nodetails_html_calls[-1][1] == "Attribute"


class TestHandleIodItemClicked:
    """Tests for AppController._handle_iod_item_clicked (uses the LoadIODDialog monkeypatch)."""

    def test_children_already_populated_returns_early_without_starting_worker(self, fake_logger):
        """An IOD row that already has children only renders details, without loading anything."""
        qt_model, index, name_item, kind_item = _iod_index_with_children(children_populated=True)
        view = FakeView(ui=FakeUi(iod_tree_view=FakeIodTreeView(model=qt_model)))
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._handle_iod_item_clicked(index, name_item, kind_item)

        assert view.details_html_calls
        assert state.iod_model_service.start_iodmodel_worker_calls == []
        assert view.status_bar_calls == []

    def test_not_yet_loaded_starts_worker_and_shows_progress_dialog(self, fake_logger, monkeypatch):
        """An IOD row with no children yet starts the model loader and shows the progress dialog."""
        monkeypatch.setattr(app_controller_module, "LoadIODDialog", FakeLoadIODDialog)
        FakeLoadIODDialog.instances.clear()
        qt_model, index, name_item, kind_item = _iod_index_with_children(children_populated=False)
        iod_tree_view = FakeIodTreeView(model=qt_model)
        view = FakeView(ui=FakeUi(iod_tree_view=iod_tree_view))
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._handle_iod_item_clicked(index, name_item, kind_item)

        assert state.iod_model_service.start_iodmodel_worker_calls == ["table_A.1-1"]
        assert len(FakeLoadIODDialog.instances) == 1
        assert FakeLoadIODDialog.instances[0].shown is True
        assert state.progress_dialog is FakeLoadIODDialog.instances[0]
        assert iod_tree_view.set_enabled_calls == [False]
        assert iod_tree_view.expand_calls == [index]
        assert view.status_bar_calls[-1] == "Loading IOD specification..."


class TestHandleModuleItemClicked:
    """Tests for AppController._handle_module_item_clicked."""

    def test_composite_iod_kind_renders_ie_and_usage(self, fake_logger):
        """A Composite IOD's module details include IE and mapped Usage, but not Description."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)
        details = {"module": "Patient", "ie": "Patient", "usage": "M", "ref": "", "description": "desc"}

        state._handle_module_item_clicked(details, "Composite")

        html = view.details_html_calls[-1]
        assert "IE:" in html
        assert "Mandatory (M)" in html
        assert "Description:" not in html

    def test_non_composite_iod_kind_renders_description_instead(self, fake_logger):
        """A non-Composite IOD's module details include Description, but not IE/Usage."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)
        details = {"module": "Patient", "ref": "", "description": "desc text"}

        state._handle_module_item_clicked(details, "Normalized")

        html = view.details_html_calls[-1]
        assert "desc text" in html
        assert "IE:" not in html

    def test_ref_html_resolved_via_model_get_module_ref_link(self, fake_logger):
        """A non-empty ref is passed through Model.get_module_ref_link before rendering."""
        model = FakeModel(module_ref_link='<a href="x">ref</a>')
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)
        details = {"module": "Patient", "ref": "<xref/>", "description": ""}

        state._handle_module_item_clicked(details, "Composite")

        assert '<a href="x">ref</a>' in view.details_html_calls[-1]


class TestHandleAttributeItemClicked:
    """Tests for AppController._handle_attribute_item_clicked."""

    def test_renders_mapped_type_display(self, fake_logger):
        """A known elem_type is rendered via DICOM_TYPE_MAP."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)
        details = {"elem_name": "PatientName", "elem_tag": "(0010,0010)", "elem_type": "1C", "elem_description": "desc"}

        state._handle_attribute_item_clicked(details)

        html = view.details_html_calls[-1]
        assert "Conditional (1C)" in html
        assert "(0010,0010)" in html

    def test_unmapped_type_falls_back_to_other(self, fake_logger):
        """An elem_type outside DICOM_TYPE_MAP is rendered as "Other (<value>)"."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)
        details = {"elem_name": "X", "elem_tag": "", "elem_type": "9", "elem_description": ""}

        state._handle_attribute_item_clicked(details)

        assert "Other (9)" in view.details_html_calls[-1]


class TestOnTreeviewRightClick:
    """Tests for AppController._on_treeview_right_click (uses the QMenu monkeypatch)."""

    def test_no_table_id_logs_warning_and_shows_no_menu(self, fake_logger, monkeypatch, caplog):
        """A row with no TABLE_ID_ROLE (e.g. a child row) logs a warning and shows nothing."""
        monkeypatch.setattr(app_controller_module, "QMenu", FakeQMenu)
        FakeQMenu.instances.clear()
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([])
        name_item = QStandardItem("NoId")
        qt_model.appendRow([name_item])
        index = qt_model.indexFromItem(name_item)
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        with caplog.at_level(logging.WARNING):
            state._on_treeview_right_click(index, global_pos="pos")

        assert FakeQMenu.instances == []
        assert "table_id" in caplog.text

    def test_menu_offers_remove_when_already_favorite(self, fake_logger, monkeypatch):
        """A favorited IOD's context menu offers "Remove from favorites"."""
        monkeypatch.setattr(app_controller_module, "QMenu", FakeQMenu)
        FakeQMenu.instances.clear()
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([entry])
        index = qt_model.indexFromItem(qt_model.item(0, 0))
        favorites = FakeFavoritesManager(favorite_table_ids={"table_A.1-1"})
        state = make_controller_state(
            view=FakeView(), model=FakeModel(), logger=fake_logger, favorites_manager=favorites
        )

        state._on_treeview_right_click(index, global_pos="pos")

        menu = FakeQMenu.instances[-1]
        assert [action.text for action in menu.actions] == ["Remove from favorites"]
        assert menu.exec_calls == ["pos"]

    def test_menu_offers_add_when_not_favorite(self, fake_logger, monkeypatch):
        """A non-favorited IOD's context menu offers "Add to favorites"."""
        monkeypatch.setattr(app_controller_module, "QMenu", FakeQMenu)
        FakeQMenu.instances.clear()
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([entry])
        index = qt_model.indexFromItem(qt_model.item(0, 0))
        favorites = FakeFavoritesManager()
        state = make_controller_state(
            view=FakeView(), model=FakeModel(), logger=fake_logger, favorites_manager=favorites
        )

        state._on_treeview_right_click(index, global_pos="pos")

        menu = FakeQMenu.instances[-1]
        assert [action.text for action in menu.actions] == ["Add to favorites"]

    def test_selecting_menu_action_toggles_favorite(self, fake_logger, monkeypatch):
        """Triggering the menu action calls back into _toggle_favorite with the row's table_id."""
        monkeypatch.setattr(app_controller_module, "QMenu", FakeQMenu)
        FakeQMenu.instances.clear()
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([entry])
        index = qt_model.indexFromItem(qt_model.item(0, 0))
        favorites = FakeFavoritesManager()
        state = make_controller_state(
            view=FakeView(), model=FakeModel(), logger=fake_logger, favorites_manager=favorites
        )

        state._on_treeview_right_click(index, global_pos="pos")
        FakeQMenu.instances[-1].actions[0].triggered.connected[0]()

        assert favorites.add_calls == ["table_A.1-1"]

    def test_export_submenu_disabled_with_tooltip_when_specmodel_not_loaded(self, fake_logger, monkeypatch):
        """The Export submenu is disabled with an explanatory tooltip if the IOD hasn't been loaded yet."""
        monkeypatch.setattr(app_controller_module, "QMenu", FakeQMenu)
        FakeQMenu.instances.clear()
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([entry])
        index = qt_model.indexFromItem(qt_model.item(0, 0))
        state = make_controller_state(
            view=FakeView(),
            model=FakeModel(iod_specmodels={}),
            logger=fake_logger,
            favorites_manager=FakeFavoritesManager(),
        )

        state._on_treeview_right_click(index, global_pos="pos")

        export_menu = FakeQMenu.instances[-1].submenus["Export"]
        assert [action.text for action in export_menu.actions] == ["CSV...", "Excel..."]
        assert export_menu.enabled is False
        assert export_menu.tool_tip == "Select this IOD first to load it"

    def test_export_submenu_enabled_when_specmodel_loaded(self, fake_logger, monkeypatch):
        """The Export submenu is enabled once the IOD's specmodel is present in Model.iod_specmodels."""
        monkeypatch.setattr(app_controller_module, "QMenu", FakeQMenu)
        FakeQMenu.instances.clear()
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([entry])
        index = qt_model.indexFromItem(qt_model.item(0, 0))
        state = make_controller_state(
            view=FakeView(),
            model=FakeModel(iod_specmodels={"table_A.1-1": "loaded_model"}),
            logger=fake_logger,
            favorites_manager=FakeFavoritesManager(),
        )

        state._on_treeview_right_click(index, global_pos="pos")

        export_menu = FakeQMenu.instances[-1].submenus["Export"]
        assert export_menu.enabled is True
        assert export_menu.tool_tip == ""

    def test_selecting_csv_export_action_calls_export_iod_model(self, fake_logger, monkeypatch):
        """Triggering the "CSV..." action calls back into _export_iod_model with fmt="csv"."""
        monkeypatch.setattr(app_controller_module, "QMenu", FakeQMenu)
        FakeQMenu.instances.clear()
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([entry])
        index = qt_model.indexFromItem(qt_model.item(0, 0))
        calls = []
        state = make_controller_state(
            view=FakeView(),
            model=FakeModel(iod_specmodels={"table_A.1-1": "loaded_model"}),
            logger=fake_logger,
            favorites_manager=FakeFavoritesManager(),
            _export_iod_model=lambda table_id, iod_name, fmt: calls.append((table_id, iod_name, fmt)),
        )

        state._on_treeview_right_click(index, global_pos="pos")
        export_menu = FakeQMenu.instances[-1].submenus["Export"]
        export_menu.actions[0].triggered.connected[0]()

        assert calls == [("table_A.1-1", "Alpha", "csv")]

    def test_selecting_excel_export_action_calls_export_iod_model(self, fake_logger, monkeypatch):
        """Triggering the "Excel..." action calls back into _export_iod_model with fmt="xlsx"."""
        monkeypatch.setattr(app_controller_module, "QMenu", FakeQMenu)
        FakeQMenu.instances.clear()
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([entry])
        index = qt_model.indexFromItem(qt_model.item(0, 0))
        calls = []
        state = make_controller_state(
            view=FakeView(),
            model=FakeModel(iod_specmodels={"table_A.1-1": "loaded_model"}),
            logger=fake_logger,
            favorites_manager=FakeFavoritesManager(),
            _export_iod_model=lambda table_id, iod_name, fmt: calls.append((table_id, iod_name, fmt)),
        )

        state._on_treeview_right_click(index, global_pos="pos")
        export_menu = FakeQMenu.instances[-1].submenus["Export"]
        export_menu.actions[1].triggered.connected[0]()

        assert calls == [("table_A.1-1", "Alpha", "xlsx")]


class TestExportSelectedIod:
    """Tests for AppController._export_selected_iod (File > Export menu actions)."""

    def test_no_selection_does_nothing(self, fake_logger):
        """With no IOD selected, no export is started."""
        calls = []
        state = make_controller_state(
            view=FakeView(selected_iod=None),
            model=FakeModel(),
            logger=fake_logger,
            _export_iod_model=lambda table_id, iod_name, fmt: calls.append((table_id, iod_name, fmt)),
        )

        state._export_selected_iod("csv")

        assert not calls

    def test_exports_the_selected_iod_in_the_given_format(self, fake_logger):
        """With an IOD selected, _export_iod_model is called with its table_id, name, and the given format."""
        calls = []
        state = make_controller_state(
            view=FakeView(selected_iod=("table_A.1-1", "Alpha")),
            model=FakeModel(),
            logger=fake_logger,
            _export_iod_model=lambda table_id, iod_name, fmt: calls.append((table_id, iod_name, fmt)),
        )

        state._export_selected_iod("xlsx")

        assert calls == [("table_A.1-1", "Alpha", "xlsx")]


class TestOnToggleFavoriteActionTriggered:
    """Tests for AppController._on_toggle_favorite_state_action_triggered (File menu action)."""

    def test_no_selection_does_nothing(self, fake_logger):
        """With no IOD selected, no favorite is toggled."""
        favorites = FakeFavoritesManager()
        state = make_controller_state(
            view=FakeView(selected_iod=None), model=FakeModel(), logger=fake_logger, favorites_manager=favorites
        )

        state._on_toggle_favorite_state_action_triggered()

        assert favorites.add_calls == []

    def test_toggles_favorite_for_the_selected_iod(self, fake_logger):
        """With an IOD selected, its favorite status is toggled."""
        favorites = FakeFavoritesManager()
        state = make_controller_state(
            view=FakeView(selected_iod=("table_A.1-1", "Alpha")),
            model=FakeModel(),
            logger=fake_logger,
            favorites_manager=favorites,
        )

        state._on_toggle_favorite_state_action_triggered()

        assert favorites.add_calls == ["table_A.1-1"]


class TestOnFileMenuAboutToShow:
    """Tests for AppController._on_file_menu_about_to_show (File menu Export/favorite enabled state)."""

    def test_no_selection_disables_export_and_favorite(self, fake_logger):
        """With no IOD selected, Export is disabled with a tooltip and the favorite action is disabled."""
        view = FakeView(selected_iod=None)
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._on_file_menu_about_to_show()

        assert view.export_menu_enabled_calls == [(False, "Select an IOD first")]
        assert view.favorite_action_calls == [(False, False)]

    def test_selected_but_not_loaded_disables_export_with_tooltip(self, fake_logger):
        """A selected but not-yet-loaded IOD disables Export with a tooltip to select it first."""
        view = FakeView(selected_iod=("table_A.1-1", "Alpha"))
        state = make_controller_state(
            view=view,
            model=FakeModel(iod_specmodels={}),
            logger=fake_logger,
            favorites_manager=FakeFavoritesManager(),
        )

        state._on_file_menu_about_to_show()

        assert view.export_menu_enabled_calls == [(False, "Select this IOD first to load it")]

    def test_selected_and_loaded_enables_export(self, fake_logger):
        """A selected, already-loaded IOD enables Export with no tooltip."""
        view = FakeView(selected_iod=("table_A.1-1", "Alpha"))
        state = make_controller_state(
            view=view,
            model=FakeModel(iod_specmodels={"table_A.1-1": "loaded_model"}),
            logger=fake_logger,
            favorites_manager=FakeFavoritesManager(),
        )

        state._on_file_menu_about_to_show()

        assert view.export_menu_enabled_calls == [(True, "")]

    def test_selected_non_favorite_enables_action_as_add(self, fake_logger):
        """A selected, non-favorited IOD enables the favorite action with is_favorite=False."""
        view = FakeView(selected_iod=("table_A.1-1", "Alpha"))
        state = make_controller_state(
            view=view, model=FakeModel(), logger=fake_logger, favorites_manager=FakeFavoritesManager()
        )

        state._on_file_menu_about_to_show()

        assert view.favorite_action_calls == [(True, False)]

    def test_selected_favorite_enables_action_as_remove(self, fake_logger):
        """A selected, already-favorited IOD enables the favorite action with is_favorite=True."""
        view = FakeView(selected_iod=("table_A.1-1", "Alpha"))
        favorites = FakeFavoritesManager(favorite_table_ids={"table_A.1-1"})
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger, favorites_manager=favorites)

        state._on_file_menu_about_to_show()

        assert view.favorite_action_calls == [(True, True)]


class TestNormalizeExportFilename:
    """Tests for AppController._normalize_export_filename."""

    def test_replaces_filesystem_unsafe_characters(self):
        """Characters invalid in filenames on common filesystems are replaced with underscores."""
        assert AppController._normalize_export_filename('A/B\\C:D*E?F"G<H>I|J') == "A_B_C_D_E_F_G_H_I_J"

    def test_replaces_spaces_with_underscores(self):
        """Spaces are replaced with underscores rather than left in the filename."""
        assert AppController._normalize_export_filename("Basic Text SR IOD") == "Basic_Text_SR_IOD"

    def test_collapses_consecutive_whitespace(self):
        """A run of consecutive whitespace collapses to a single underscore."""
        assert AppController._normalize_export_filename("A   B") == "A_B"

    def test_blank_name_falls_back_to_export(self):
        """An empty or whitespace-only name falls back to a generic default."""
        assert AppController._normalize_export_filename("   ") == "export"


class TestExportIodModel:
    """Tests for AppController._export_iod_model."""

    def test_cancelled_dialog_starts_no_worker(self, fake_logger):
        """A None path (dialog cancelled) starts no export worker and leaves the status bar alone."""
        view = FakeView(save_file_return=None)
        state = make_controller_state(
            view=view, model=FakeModel(iod_specmodels={"table_A.1-1": "loaded_model"}), logger=fake_logger
        )

        state._export_iod_model("table_A.1-1", "Alpha", "csv")

        assert state.export_service.start_export_worker_calls == []
        assert view.status_bar_calls == []

    def test_csv_export_starts_worker_with_right_args(self, fake_logger):
        """A confirmed CSV export starts the worker with the loaded specmodel, format, and chosen path."""
        view = FakeView(save_file_return="/tmp/Alpha.csv")
        state = make_controller_state(
            view=view, model=FakeModel(iod_specmodels={"table_A.1-1": "loaded_model"}), logger=fake_logger
        )

        state._export_iod_model("table_A.1-1", "Alpha", "csv")

        assert state.export_service.start_export_worker_calls == [("loaded_model", "csv", "/tmp/Alpha.csv")]
        assert view.status_bar_calls == ["Exporting..."]
        _, default_name, file_filter = view.prompt_save_file_calls[0]
        assert default_name == "Alpha.csv"
        assert file_filter == "CSV files (*.csv)"

    def test_xlsx_export_uses_xlsx_default_name_and_filter(self, fake_logger):
        """A confirmed Excel export proposes a .xlsx default filename and filter."""
        view = FakeView(save_file_return="/tmp/Alpha.xlsx")
        state = make_controller_state(
            view=view, model=FakeModel(iod_specmodels={"table_A.1-1": "loaded_model"}), logger=fake_logger
        )

        state._export_iod_model("table_A.1-1", "Alpha", "xlsx")

        assert state.export_service.start_export_worker_calls == [("loaded_model", "xlsx", "/tmp/Alpha.xlsx")]
        _, default_name, file_filter = view.prompt_save_file_calls[0]
        assert default_name == "Alpha.xlsx"
        assert file_filter == "Excel files (*.xlsx)"


class TestHandleExportLoaded:
    """Tests for AppController._handle_export_loaded."""

    def test_updates_status_bar_with_output_path(self, fake_logger):
        """A successful export updates the status bar with the written file's path."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._handle_export_loaded(sender=object(), output_path="/tmp/Alpha.csv")

        assert view.status_bar_calls == ["Exported to /tmp/Alpha.csv"]


class TestHandleExportError:
    """Tests for AppController._handle_export_error."""

    def test_shows_error_and_updates_status_bar(self, fake_logger, caplog):
        """A failed export logs the error, shows it to the user, and updates the status bar."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        with caplog.at_level(logging.ERROR):
            state._handle_export_error(sender=object(), message="disk full")

        assert view.error_calls == ["disk full"]
        assert view.status_bar_calls == ["Error exporting IOD."]


class TestToggleFavorite:
    """Tests for AppController._toggle_favorite."""

    def test_adds_favorite_when_not_already_favorite(self, fake_logger):
        """A non-favorited table_id gets added, then the treeview is rebuilt."""
        favorites = FakeFavoritesManager()
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger, favorites_manager=favorites)

        state._toggle_favorite("table_A.1-1")

        assert favorites.add_calls == ["table_A.1-1"]
        assert favorites.remove_calls == []
        assert view.update_treeview_calls

    def test_removes_favorite_when_already_favorite(self, fake_logger):
        """An already-favorited table_id gets removed, then the treeview is rebuilt."""
        favorites = FakeFavoritesManager(favorite_table_ids={"table_A.1-1"})
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger, favorites_manager=favorites)

        state._toggle_favorite("table_A.1-1")

        assert favorites.remove_calls == ["table_A.1-1"]
        assert favorites.add_calls == []

    def test_shows_error_without_reraising_when_favorites_manager_raises(self, fake_logger):
        """A FavoritesManager failure is shown as an error dialog, not propagated."""
        favorites = FakeFavoritesManager(raise_on_add=RuntimeError("disk full"))
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger, favorites_manager=favorites)

        state._toggle_favorite("table_A.1-1")  # must not raise

        assert view.error_calls == ["Failed to update favorites."]
        assert view.update_treeview_calls


class TestHandleIodlistProgress:
    """Tests for AppController._handle_iodlist_progress."""

    def test_unknown_progress_shows_unknown_message(self, fake_logger):
        """percent=-1 (unknown) shows a distinct status bar message."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._handle_iodlist_progress(sender=object(), progress=Progress(percent=-1))

        assert view.status_bar_calls[-1] == "Loading IOD modules... (unknown progress)"

    def test_percent_multiple_of_ten_updates_status_bar(self, fake_logger):
        """A percent that's a multiple of 10 updates the status bar."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._handle_iodlist_progress(sender=object(), progress=Progress(percent=30))

        assert view.status_bar_calls[-1] == "Loading IOD modules... 30%"

    def test_percent_not_multiple_of_ten_or_100_does_not_update_status_bar(self, fake_logger):
        """A percent that's neither a multiple of 10 nor 100 is silently dropped."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._handle_iodlist_progress(sender=object(), progress=Progress(percent=37))

        assert view.status_bar_calls == []


class TestHandleIodlistLoaded:
    """Tests for AppController._handle_iodlist_loaded."""

    def test_delegates_to_apply_filter_and_sort(self, fake_logger):
        """The loaded entries are passed through to rebuild the treeview."""
        entries = [IODEntry("Alpha", "table_A.1-1", "url", "Composite")]
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._handle_iodlist_loaded(sender=object(), iod_entry_list=entries)

        assert view.update_treeview_calls[-1].rowCount() == 1

    def test_populates_already_loaded_children_twice_when_no_new_version(self, fake_logger):
        """Characterizes current (buggy) behavior, not fixed here.

        build_treeview_model (called via apply_filter_and_sort) already populates children for
        every already-loaded IOD. When no new version is available, this handler unconditionally
        repeats that same population, so the children end up duplicated. Pinned down as-is, per
        this project's "test current behavior, don't fix bugs" rule.
        """
        entry = IODEntry("Alpha", "table_A.1-1", "url", "Composite")
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"
        model = FakeModel(iod_specmodels={"table_A.1-1": FakeIodModel(content)}, new_version_available=False)
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state._handle_iodlist_loaded(sender=object(), iod_entry_list=[entry])

        assert view.ui.iodTreeView.model().item(0, 0).rowCount() == 2

    def test_does_not_repeat_population_when_new_version_available(self, fake_logger):
        """When a new version is available, the extra (duplicating) population pass is skipped."""
        entry = IODEntry("Alpha", "table_A.1-1", "url", "Composite")
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"
        model = FakeModel(iod_specmodels={"table_A.1-1": FakeIodModel(content)}, new_version_available=True)
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state._handle_iodlist_loaded(sender=object(), iod_entry_list=[entry])

        assert view.ui.iodTreeView.model().item(0, 0).rowCount() == 1

    def test_updates_version_label_when_model_has_version(self, fake_logger):
        """A non-empty Model.version updates the version label."""
        model = FakeModel(version="2024e")
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state._handle_iodlist_loaded(sender=object(), iod_entry_list=[])

        assert view.ui.versionLabel.set_text_calls[-1] == "Version: 2024e"

    def test_shows_new_version_info_dialog_when_new_version_available(self, fake_logger):
        """A new version shows an info dialog and a distinct status bar message."""
        model = FakeModel(new_version_available=True)
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state._handle_iodlist_loaded(sender=object(), iod_entry_list=[])

        assert view.info_calls
        assert "updated" in view.status_bar_calls[-1].lower()

    def test_shows_normal_count_message_when_no_new_version(self, fake_logger):
        """With no new version, the status bar shows a plain IOD count instead."""
        entries = [IODEntry("Alpha", "table_A.1-1", "url", "Composite")] * 3
        model = FakeModel(new_version_available=False)
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        state._handle_iodlist_loaded(sender=object(), iod_entry_list=entries)

        assert view.status_bar_calls[-1] == "Listed 3 IODs."
        assert view.info_calls == []

    def test_raises_if_iod_specmodels_mutated_during_iteration(self, fake_logger):
        """Hazard test characterizing a dict mutated during iteration.

        A hostile dict that mutates itself mid-iteration reproduces the same RuntimeError CPython
        raises for a real dict mutated during a concurrent load/reload race on
        Model._iod_specmodels, deterministically and without a real thread race.
        """
        entry = IODEntry("Alpha", "table_A.1-1", "url", "Composite")
        hostile_specmodels = HostileSpecModelsDict({"table_A.1-1": object()})
        model = FakeModel(iod_specmodels=hostile_specmodels, new_version_available=False)
        view = FakeView()
        state = make_controller_state(view=view, model=model, logger=fake_logger)

        with pytest.raises(RuntimeError, match="dictionary changed size during iteration"):
            state._handle_iodlist_loaded(sender=object(), iod_entry_list=[entry])


class TestHandleIodlistError:
    """Tests for AppController._handle_iodlist_error."""

    def test_logs_shows_error_and_updates_status_bar(self, fake_logger, caplog):
        """An error event is logged, shown to the user, and reflected in the status bar."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        with caplog.at_level(logging.ERROR):
            state._handle_iodlist_error(sender="mediator", message="boom")

        assert view.error_calls == ["boom"]
        assert view.status_bar_calls[-1] == "Error loading IOD modules."
        assert "boom" in caplog.text


class TestHandleIodmodelProgress:
    """Tests for AppController._handle_iodmodel_progress."""

    def test_updates_progress_dialog_step_when_present(self, fake_logger):
        """With a progress dialog set, its step is updated with the status and percent."""
        dialog = FakeLoadIODDialog(parent=None)
        state = make_controller_state(view=FakeView(), model=FakeModel(), logger=fake_logger, progress_dialog=dialog)
        progress = Progress(status=ProgressStatus.DOWNLOADING_IOD, percent=40, step=1, total_steps=4)

        state._handle_iodmodel_progress(sender=object(), progress=progress)

        assert dialog.update_step_calls == [(ProgressStatus.DOWNLOADING_IOD, 40)]

    def test_no_progress_dialog_does_not_raise(self, fake_logger):
        """With no progress dialog set, the event is silently ignored."""
        state = make_controller_state(view=FakeView(), model=FakeModel(), logger=fake_logger, progress_dialog=None)
        progress = Progress(status=ProgressStatus.DOWNLOADING_IOD, percent=40, step=1, total_steps=4)

        state._handle_iodmodel_progress(sender=object(), progress=progress)  # must not raise


class TestHandleIodmodelLoaded:
    """Tests for AppController._handle_iodmodel_loaded."""

    def test_populates_children_hides_dialog_and_reenables_treeview(self, fake_logger):
        """A successful load populates the matching row's children and tidies up the UI state."""
        entry = IODEntry("Alpha", "table_A.1-1", "url", "Composite")
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([entry])
        iod_tree_view = FakeIodTreeView(model=qt_model)
        view = FakeView(ui=FakeUi(iod_tree_view=iod_tree_view))
        dialog = FakeLoadIODDialog(parent=None)
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger, progress_dialog=dialog)
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"

        state._handle_iodmodel_loaded(sender=object(), iod_model=FakeIodModel(content), table_id="table_A.1-1")

        assert qt_model.item(0, 0).rowCount() == 1
        assert dialog.accepted is True
        assert state.progress_dialog is None
        assert iod_tree_view.set_enabled_calls == [True]
        assert view.status_bar_calls[-1] == "IOD specification loaded."

    def test_shows_error_when_table_id_no_longer_visible(self, fake_logger):
        """A table_id no longer present in the (e.g. filtered) treeview shows a specific error."""
        qt_model = IODTreeViewModelAdapter().populate_treeview_model_top_level([])
        view = FakeView(ui=FakeUi(iod_tree_view=FakeIodTreeView(model=qt_model)))
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger, progress_dialog=None)

        state._handle_iodmodel_loaded(
            sender=object(), iod_model=FakeIodModel(Node("content")), table_id="table_missing"
        )

        assert view.error_calls == ["The selected IOD is no longer visible. Please clear the filter and try again."]

    def test_no_content_attribute_does_nothing(self, fake_logger):
        """An iod_model with no .content attribute is entirely ignored."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._handle_iodmodel_loaded(sender=object(), iod_model=object(), table_id="table_A.1-1")

        assert view.status_bar_calls == []


class TestHandleIodmodelError:
    """Tests for AppController._handle_iodmodel_error."""

    def test_hides_dialog_reenables_treeview_and_shows_error(self, fake_logger, caplog):
        """An error event tidies up the UI state and shows the error to the user."""
        dialog = FakeLoadIODDialog(parent=None)
        iod_tree_view = FakeIodTreeView()
        view = FakeView(ui=FakeUi(iod_tree_view=iod_tree_view))
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger, progress_dialog=dialog)

        with caplog.at_level(logging.ERROR):
            state._handle_iodmodel_error(sender=object(), message="bad table_id")

        assert dialog.rejected is True
        assert state.progress_dialog is None
        assert iod_tree_view.set_enabled_calls == [True]
        assert view.error_calls == ["bad table_id"]
        assert view.status_bar_calls[-1] == "Error loading IOD specification."

    def test_no_progress_dialog_does_not_raise(self, fake_logger):
        """With no progress dialog set, cleanup is skipped but the error is still shown."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger, progress_dialog=None)

        state._handle_iodmodel_error(sender=object(), message="bad")  # must not raise

        assert view.error_calls == ["bad"]


class TestOnDetailsLinkClicked:
    """Tests for AppController._on_details_link_clicked."""

    def test_fragment_only_url_shows_anchor_warning(self, fake_logger):
        """A same-page anchor link (e.g. "#section1") shows the anchor-not-supported dialog."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._on_details_link_clicked(QUrl("#section1"))

        assert view.anchor_warning_calls == ["#section1"]
        assert view.url_warning_calls == []

    def test_external_url_shows_url_warning(self, fake_logger):
        """A full external URL shows the "open external link" confirmation dialog."""
        view = FakeView()
        state = make_controller_state(view=view, model=FakeModel(), logger=fake_logger)

        state._on_details_link_clicked(QUrl("http://example.com/page"))

        assert view.url_warning_calls == ["http://example.com/page"]
        assert view.anchor_warning_calls == []
