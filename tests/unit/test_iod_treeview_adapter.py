"""Unit tests for dcmspec_explorer.controller.iod_treeview_adapter.IODTreeViewModelAdapter."""

import pytest
from anytree import Node
from PySide6.QtGui import QStandardItem, QIcon, QPixmap, QColor

from dcmspec_explorer.controller.iod_treeview_adapter import IODTreeViewModelAdapter, COLUMN_INDEX
from dcmspec_explorer.model.model import IODEntry
from dcmspec_explorer.qt.qt_roles import TABLE_ID_ROLE, TABLE_URL_ROLE, NODE_PATH_ROLE, IS_FAVORITE_ROLE


def _plain_standard_item():
    """Return a fresh QStandardItem with no data set, for building item trees by hand."""
    return QStandardItem()


def _solid_icon(color):
    """Return a QIcon wrapping a small solid-color pixmap, distinguishable from other icons."""
    pixmap = QPixmap(4, 4)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def _standard_item_with_table_id(table_id):
    """Return a QStandardItem with TABLE_ID_ROLE set to table_id."""
    item = _plain_standard_item()
    item.setData(table_id, TABLE_ID_ROLE)
    return item


class FakeFavoritesManager:
    """Fake favorites manager backed by a plain set, avoiding file I/O for adapter tests."""

    def __init__(self, favorite_table_ids=None):
        """Initialize with the given table_ids (or none) marked as favorites."""
        self._favorites = set(favorite_table_ids or [])

    def is_favorite(self, table_id):
        """Return whether table_id is in the favorites set."""
        return table_id in self._favorites


class FakeIodModel:
    """Fake loaded IOD spec model exposing only the .content attribute the adapter reads."""

    def __init__(self, content):
        """Initialize with the given anytree content root."""
        self.content = content


class FakeDataModel:
    """Fake data model exposing only the .iod_specmodels property and cache-check the adapter reads."""

    def __init__(self, iod_specmodels=None, cached_table_ids=None):
        """Initialize with the given table_id -> FakeIodModel mapping and cached table_ids."""
        self.iod_specmodels = iod_specmodels or {}
        self._cached_table_ids = set(cached_table_ids or [])

    def is_iod_model_cached(self, table_id):
        """Return whether table_id is in the cached table_ids set."""
        return table_id in self._cached_table_ids


@pytest.fixture
def iod_entries():
    """Return three IODEntry fixtures spanning two kinds, for filter/sort tests."""
    # "alpha" is deliberately lowercase while the others are capitalized: a sort that
    # compares iod.name directly instead of iod.name.lower() would order these
    # entries differently, so the mixed case is what lets the sort tests catch that.
    return [
        IODEntry("Beta Image", "table_B.1-1", "http://example.com/b", "Normalized"),
        IODEntry("alpha Image", "table_A.1-1", "http://example.com/a", "Composite"),
        IODEntry("Gamma Image", "table_G.1-1", "http://example.com/g", "Composite"),
    ]


class TestGetTableIdForItem:
    """Tests for IODTreeViewModelAdapter.get_table_id_for_item."""

    def test_returns_table_id_from_top_level_item(self):
        """A top-level item with TABLE_ID_ROLE set returns it directly."""
        item = _standard_item_with_table_id("table_A.1-1")

        assert IODTreeViewModelAdapter.get_table_id_for_item(item) == "table_A.1-1"

    def test_walks_up_parent_chain_to_find_table_id_from_child_item(self):
        """A grandchild item with no TABLE_ID_ROLE of its own returns the ancestor's table_id."""
        top_item = _standard_item_with_table_id("table_A.1-1")
        child_item = _plain_standard_item()
        grandchild_item = _plain_standard_item()
        top_item.appendRow([child_item])
        child_item.appendRow([grandchild_item])

        assert IODTreeViewModelAdapter.get_table_id_for_item(grandchild_item) == "table_A.1-1"

    def test_returns_none_when_no_ancestor_has_a_table_id(self):
        """A standalone item with no TABLE_ID_ROLE anywhere in its chain returns None."""
        item = _plain_standard_item()

        assert IODTreeViewModelAdapter.get_table_id_for_item(item) is None


class TestBuildTreeviewModelFiltering:
    """Tests for IODTreeViewModelAdapter.build_treeview_model's search-text filtering."""

    def test_no_search_text_returns_all_entries(self, iod_entries):
        """An empty search_text keeps every entry."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model(iod_entries, data_model, search_text="")

        assert qt_model.rowCount() == len(iod_entries)

    def test_search_text_matches_name_case_sensitively(self, iod_entries):
        """A case-matching substring of the name keeps the entry; a case mismatch excludes it."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        matching_model, _ = adapter.build_treeview_model(iod_entries, data_model, search_text="Beta")
        mismatched_model, _ = adapter.build_treeview_model(iod_entries, data_model, search_text="beta")

        assert [matching_model.item(r, 0).text() for r in range(matching_model.rowCount())] == ["Beta Image"]
        assert mismatched_model.rowCount() == 0

    def test_search_text_matches_kind(self, iod_entries):
        """A substring matching the kind also keeps the entry."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model(iod_entries, data_model, search_text="Normalized")

        names = [qt_model.item(row, 0).text() for row in range(qt_model.rowCount())]
        assert names == ["Beta Image"]

    def test_search_text_is_stripped_before_matching(self, iod_entries):
        """Leading/trailing whitespace in search_text is stripped before matching."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model(iod_entries, data_model, search_text="  Beta  ")

        assert qt_model.rowCount() == 1


class TestBuildTreeviewModelSorting:
    """Tests for IODTreeViewModelAdapter.build_treeview_model's sorting behavior."""

    def test_sort_by_name_ascending(self, iod_entries):
        """sort_column=name, sort_reverse=False sorts case-insensitively by name ascending."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model(
            iod_entries, data_model, sort_column=COLUMN_INDEX["name"], sort_reverse=False
        )

        names = [qt_model.item(row, 0).text() for row in range(qt_model.rowCount())]
        assert names == ["alpha Image", "Beta Image", "Gamma Image"]

    def test_sort_by_name_descending(self, iod_entries):
        """sort_column=name, sort_reverse=True sorts case-insensitively by name descending."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model(
            iod_entries, data_model, sort_column=COLUMN_INDEX["name"], sort_reverse=True
        )

        names = [qt_model.item(row, 0).text() for row in range(qt_model.rowCount())]
        assert names == ["Gamma Image", "Beta Image", "alpha Image"]

    def test_sort_by_kind_then_name_ascending(self, iod_entries):
        """sort_column=kind sorts by kind first, then by name as a tiebreaker, ascending."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model(
            iod_entries, data_model, sort_column=COLUMN_INDEX["kind"], sort_reverse=False
        )

        names = [qt_model.item(row, 0).text() for row in range(qt_model.rowCount())]
        assert names == ["alpha Image", "Gamma Image", "Beta Image"]

    def test_sort_by_kind_then_name_descending(self, iod_entries):
        """sort_column=kind, sort_reverse=True reverses both the kind grouping and the name tiebreaker."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model(
            iod_entries, data_model, sort_column=COLUMN_INDEX["kind"], sort_reverse=True
        )

        names = [qt_model.item(row, 0).text() for row in range(qt_model.rowCount())]
        assert names == ["Beta Image", "Gamma Image", "alpha Image"]

    def test_sort_column_none_preserves_input_order(self, iod_entries):
        """sort_column=None (the startup state) applies no sorting at all."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model(iod_entries, data_model, sort_column=None)

        names = [qt_model.item(row, 0).text() for row in range(qt_model.rowCount())]
        assert names == [iod.name for iod in iod_entries]


class TestBuildTreeviewModelTopLevelRows:
    """Tests for IODTreeViewModelAdapter.populate_treeview_model_top_level's row contents."""

    def test_favorite_flag_role_true_for_favorite_entries(self):
        """IS_FAVORITE_ROLE is True on the favorite-column item for a favorited table_id."""
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        adapter = IODTreeViewModelAdapter(favorites_manager=FakeFavoritesManager({"table_A.1-1"}))

        model = adapter.populate_treeview_model_top_level([entry])

        favorite_item = model.item(0, COLUMN_INDEX["favorite"])
        assert favorite_item.data(IS_FAVORITE_ROLE) is True

    def test_favorite_flag_role_false_for_non_favorite_entries(self):
        """IS_FAVORITE_ROLE is False on the favorite-column item for a non-favorited table_id."""
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        adapter = IODTreeViewModelAdapter(favorites_manager=FakeFavoritesManager())

        model = adapter.populate_treeview_model_top_level([entry])

        favorite_item = model.item(0, COLUMN_INDEX["favorite"])
        assert favorite_item.data(IS_FAVORITE_ROLE) is False

    def test_no_favorites_manager_treats_all_entries_as_non_favorite(self):
        """With favorites_manager=None, the favorite role is False (not just falsy) for every entry."""
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        adapter = IODTreeViewModelAdapter(favorites_manager=None)

        model = adapter.populate_treeview_model_top_level([entry])

        favorite_item = model.item(0, COLUMN_INDEX["favorite"])
        assert favorite_item.data(IS_FAVORITE_ROLE) is False

    def test_table_id_and_table_url_stored_on_name_item(self):
        """TABLE_ID_ROLE and TABLE_URL_ROLE are set on the name-column item, not other columns."""
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        adapter = IODTreeViewModelAdapter()

        model = adapter.populate_treeview_model_top_level([entry])

        name_item = model.item(0, COLUMN_INDEX["name"])
        kind_item = model.item(0, COLUMN_INDEX["kind"])
        assert name_item.data(TABLE_ID_ROLE) == "table_A.1-1"
        assert name_item.data(TABLE_URL_ROLE) == "http://example.com/a"
        assert kind_item.data(TABLE_ID_ROLE) is None


class TestBuildTreeviewModelAlreadyLoadedChildren:
    """Tests for IODTreeViewModelAdapter.build_treeview_model's child-population from data_model."""

    def test_populates_children_for_iod_already_present_in_data_model(self, iod_entries):
        """An IOD with a matching, already-loaded specmodel gets its children populated."""
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"
        data_model = FakeDataModel({"table_A.1-1": FakeIodModel(content)})
        adapter = IODTreeViewModelAdapter()

        qt_model, _ = adapter.build_treeview_model(iod_entries, data_model)

        alpha_row = next(
            row for row in range(qt_model.rowCount()) if qt_model.item(row, 0).data(TABLE_ID_ROLE) == "table_A.1-1"
        )
        assert qt_model.item(alpha_row, 0).rowCount() == 1

    def test_does_not_populate_children_for_iod_not_yet_loaded(self, iod_entries):
        """An IOD with no entry in data_model.iod_specmodels keeps zero children."""
        data_model = FakeDataModel({})
        adapter = IODTreeViewModelAdapter()

        qt_model, _ = adapter.build_treeview_model(iod_entries, data_model)

        child_counts = [qt_model.item(row, 0).rowCount() for row in range(qt_model.rowCount())]
        assert child_counts == [0] * len(iod_entries)

    def test_selected_table_id_returns_matching_row_index(self, iod_entries):
        """A selected_table_id matching a displayed entry returns its row index."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        qt_model, selected_row = adapter.build_treeview_model(iod_entries, data_model, selected_table_id="table_G.1-1")

        assert qt_model.item(selected_row, 0).data(TABLE_ID_ROLE) == "table_G.1-1"

    def test_selected_table_id_not_present_returns_none(self, iod_entries):
        """A selected_table_id filtered out of the results (e.g. by search) returns None."""
        adapter = IODTreeViewModelAdapter()
        data_model = FakeDataModel()

        _, selected_row = adapter.build_treeview_model(
            iod_entries, data_model, search_text="Beta", selected_table_id="table_G.1-1"
        )

        assert selected_row is None


class TestBuildTreeviewModelCacheStatusIcon:
    """Tests for IODTreeViewModelAdapter.build_treeview_model's per-row cache-status icon."""

    def test_cached_table_id_gets_cached_icon(self, qapp):
        """A row whose table_id is reported cached by data_model shows the cached icon."""
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        cached_icon = _solid_icon("green")
        uncached_icon = _solid_icon("gray")
        adapter = IODTreeViewModelAdapter(cached_icon=cached_icon, uncached_icon=uncached_icon)
        data_model = FakeDataModel(cached_table_ids={"table_A.1-1"})

        qt_model, _ = adapter.build_treeview_model([entry], data_model)

        status_item = qt_model.item(0, COLUMN_INDEX["status"])
        assert status_item.icon().cacheKey() == cached_icon.cacheKey()

    def test_uncached_table_id_gets_uncached_icon(self, qapp):
        """A row whose table_id is not reported cached by data_model shows the uncached icon."""
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        cached_icon = _solid_icon("green")
        uncached_icon = _solid_icon("gray")
        adapter = IODTreeViewModelAdapter(cached_icon=cached_icon, uncached_icon=uncached_icon)
        data_model = FakeDataModel()

        qt_model, _ = adapter.build_treeview_model([entry], data_model)

        status_item = qt_model.item(0, COLUMN_INDEX["status"])
        assert status_item.icon().cacheKey() == uncached_icon.cacheKey()


class TestPopulateTreeviewModelItem:
    """Tests for IODTreeViewModelAdapter.populate_treeview_model_item's anytree traversal."""

    def test_module_node_produces_module_row_with_usage_first_letter(self):
        """A node with a .module attribute produces a Module row whose usage is usage[:1]."""
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"
        parent_item = _plain_standard_item()

        IODTreeViewModelAdapter.populate_treeview_model_item(parent_item, content)

        assert parent_item.rowCount() == 1
        assert parent_item.child(0, 0).text() == "Patient"
        assert parent_item.child(0, COLUMN_INDEX["kind"]).text() == "Module"
        assert parent_item.child(0, COLUMN_INDEX["usage"]).text() == "M"

    def test_attribute_node_produces_attribute_row_with_tag_and_name(self):
        """A node with an .elem_name attribute and a tag produces an "{tag} {name}" Attribute row."""
        content = Node("content")
        attribute = Node("PatientNameAttr", parent=content)
        attribute.elem_name = "PatientName"
        attribute.elem_tag = "(0010,0010)"
        attribute.elem_type = "1"
        parent_item = _plain_standard_item()

        IODTreeViewModelAdapter.populate_treeview_model_item(parent_item, content)

        assert parent_item.child(0, 0).text() == "(0010,0010) PatientName"
        assert parent_item.child(0, COLUMN_INDEX["kind"]).text() == "Attribute"
        assert parent_item.child(0, COLUMN_INDEX["usage"]).text() == "1"

    def test_attribute_node_without_tag_shows_name_only(self):
        """An empty elem_tag falls back to showing the bare elem_name."""
        content = Node("content")
        attribute = Node("PatientNameAttr", parent=content)
        attribute.elem_name = "PatientName"
        attribute.elem_tag = ""
        attribute.elem_type = "1"
        parent_item = _plain_standard_item()

        IODTreeViewModelAdapter.populate_treeview_model_item(parent_item, content)

        assert parent_item.child(0, 0).text() == "PatientName"

    def test_nested_modules_and_attributes_build_correct_parent_child_hierarchy(self):
        """A Module -> Attribute -> Attribute tree nests each node under its real anytree parent."""
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"
        attribute = Node("PatientNameAttr", parent=module)
        attribute.elem_name = "PatientName"
        attribute.elem_tag = ""
        attribute.elem_type = "1"
        nested_attribute = Node("ValueAttr", parent=attribute)
        nested_attribute.elem_name = "Value"
        nested_attribute.elem_tag = ""
        nested_attribute.elem_type = "1C"
        parent_item = _plain_standard_item()

        IODTreeViewModelAdapter.populate_treeview_model_item(parent_item, content)

        module_item = parent_item.child(0, 0)
        assert module_item.rowCount() == 1
        attribute_item = module_item.child(0, 0)
        assert attribute_item.text() == "PatientName"
        assert attribute_item.rowCount() == 1
        assert attribute_item.child(0, 0).text() == "Value"

    def test_node_path_role_stores_slash_joined_path_from_root(self):
        """NODE_PATH_ROLE stores "/".join(n.name for n in node.path).

        This is a cross-layer contract: AppController.get_selected_item_details reads
        this same role back off the clicked QStandardItem, strips the leading "content"
        segment, and passes the rest to Model.get_node_public_attrs as the relative path.
        If this format ever changed here without a matching change there, that lookup
        would break silently (return None) rather than fail loudly.
        """
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"
        parent_item = _plain_standard_item()

        IODTreeViewModelAdapter.populate_treeview_model_item(parent_item, content)

        assert parent_item.child(0, 0).data(NODE_PATH_ROLE) == "content/PatientModule"

    def test_child_row_status_column_carries_no_icon(self):
        """A Module/Attribute child row's status-column item is blank: cache status is IOD-level only."""
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"
        parent_item = _plain_standard_item()

        IODTreeViewModelAdapter.populate_treeview_model_item(parent_item, content)

        status_item = parent_item.child(0, COLUMN_INDEX["status"])
        assert status_item.icon().isNull()


class TestPopulateIodEntryChildren:
    """Tests for IODTreeViewModelAdapter.populate_iod_entry_children."""

    def test_returns_true_and_populates_matching_top_level_item(self):
        """A matching table_id is found among top-level rows and its children are populated."""
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        adapter = IODTreeViewModelAdapter()
        tree_model = adapter.populate_treeview_model_top_level([entry])
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        module.usage = "Mandatory"

        result = adapter.populate_iod_entry_children(tree_model, "table_A.1-1", content)

        assert result is True
        assert tree_model.item(0, 0).rowCount() == 1

    def test_returns_false_when_table_id_not_found(self):
        """A table_id with no matching top-level row (e.g. filtered out) returns False."""
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        adapter = IODTreeViewModelAdapter()
        tree_model = adapter.populate_treeview_model_top_level([entry])
        content = Node("content")

        result = adapter.populate_iod_entry_children(tree_model, "table_unknown", content)

        assert result is False

    def test_sets_status_column_icon_to_cached_on_successful_populate(self, qapp):
        """A successful populate refreshes the row's status-column icon to cached_icon.

        Regression test: a successful load always means the model is now on disk, whether it
        started cached or not, so the icon must flip immediately rather than staying stale
        until some unrelated later rebuild.
        """
        entry = IODEntry("Alpha", "table_A.1-1", "http://example.com/a", "Composite")
        cached_icon = _solid_icon("green")
        uncached_icon = _solid_icon("gray")
        adapter = IODTreeViewModelAdapter(cached_icon=cached_icon, uncached_icon=uncached_icon)
        tree_model = adapter.populate_treeview_model_top_level([entry])
        # Start the row off showing the uncached icon, as build_treeview_model would for an
        # IOD not yet cached, so the transition (not just the end state) is actually verified.
        tree_model.item(0, COLUMN_INDEX["status"]).setIcon(uncached_icon)
        content = Node("content")

        adapter.populate_iod_entry_children(tree_model, "table_A.1-1", content)

        status_item = tree_model.item(0, COLUMN_INDEX["status"])
        assert status_item.icon().cacheKey() == cached_icon.cacheKey()
