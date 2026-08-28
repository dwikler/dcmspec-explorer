"""Unit tests for the pure parsing logic in dcmspec_explorer.model.model.Model."""

import os
from urllib.parse import urljoin

import pytest
from anytree import Node
from bs4 import BeautifulSoup
from dcmspec.spec_model import SpecModel

from dcmspec_explorer.model.model import IODEntry, Model

from .fixtures_iod_list import list_of_tables_soup


@pytest.fixture
def model(make_config, fake_logger):
    """Return a Model instance backed by a real, tmp_path-isolated Config.

    Model.__init__ constructs a real dcmspec.xhtml_doc_handler.XHTMLDocHandler, which
    validates its config argument via isinstance(config, dcmspec.config.Config) -- a
    duck-typed stub is rejected, so every Model test needs a real Config even though none
    of the methods under test here perform network I/O.
    """
    return Model(config=make_config(), logger=fake_logger)


@pytest.fixture
def list_of_tables_div():
    """Return the <div class="list-of-tables"> element from the real excerpt fixture."""
    return list_of_tables_soup().find("div", class_="list-of-tables")


def _base_url(model):
    return model.part3_toc_url.rsplit("/", 1)[0] + "/"


class TestExtractIodList:
    """Tests for Model._extract_iod_list against a real DICOM PS3.3 markup excerpt."""

    def test_returns_composite_kind_for_a_prefixed_table_id(self, model, list_of_tables_div):
        """A table_id containing '_A.' is classified as a Composite IOD."""
        entries = model._extract_iod_list(list_of_tables_div)
        entry = next(e for e in entries if e.table_id == "table_A.2-1")
        assert entry.kind == "Composite"

    def test_returns_normalized_kind_for_b_prefixed_table_id(self, model, list_of_tables_div):
        """A table_id containing '_B.' is classified as a Normalized IOD."""
        entries = model._extract_iod_list(list_of_tables_div)
        entry = next(e for e in entries if e.table_id == "table_B.7-1")
        assert entry.kind == "Normalized"

    def test_returns_other_kind_for_neither_a_nor_b_table_id(self, model, list_of_tables_div):
        """A table_id containing neither '_A.' nor '_B.' is classified as Other."""
        entries = model._extract_iod_list(list_of_tables_div)
        entry = next(e for e in entries if e.table_id == "table_F.3-1")
        assert entry.kind == "Other"

    def test_strips_numeric_prefix_and_iod_modules_suffix_from_name(self, model, list_of_tables_div):
        """The table-number prefix and trailing ' IOD Modules' are stripped from the name."""
        entries = model._extract_iod_list(list_of_tables_div)
        entry = next(e for e in entries if e.table_id == "table_A.2-1")
        assert entry.name == "Computed Radiography Image"

    def test_builds_table_url_by_joining_href_to_part3_toc_base(self, model, list_of_tables_div):
        """table_url is the href resolved against the Part 3 table-of-contents base URL."""
        entries = model._extract_iod_list(list_of_tables_div)
        entry = next(e for e in entries if e.table_id == "table_A.2-1")
        expected = urljoin(_base_url(model), "sect_A.2.3.html#table_A.2-1")
        assert entry.table_url == expected

    def test_skips_dt_entries_without_iod_modules_in_anchor_text(self, model, list_of_tables_div):
        """Entries whose anchor text doesn't contain 'IOD Modules' are not included."""
        entries = model._extract_iod_list(list_of_tables_div)
        table_ids = {e.table_id for e in entries}
        assert "table_5.4-1" not in table_ids
        assert "table_8.8-1" not in table_ids

    def test_returns_exactly_the_iod_modules_entries_in_the_fixture(self, model, list_of_tables_div):
        """Only the three real IOD-Modules entries in the fixture are extracted."""
        entries = model._extract_iod_list(list_of_tables_div)
        assert {e.table_id for e in entries} == {"table_A.2-1", "table_B.7-1", "table_F.3-1"}

    def test_missing_hash_in_href_uses_placeholder_table_id_and_logs_warning(self, model, caplog):
        """Synthetic case (no real DICOM markup lacks a '#'): missing fragment is handled."""
        html = (
            '<div class="list-of-tables"><dl><dt>X.1-1. <a href="sect_X.html">No Hash IOD Modules</a></dt></dl></div>'
        )
        div = BeautifulSoup(html, "html.parser").find("div", class_="list-of-tables")
        with caplog.at_level("WARNING"):
            entries = model._extract_iod_list(div)
        assert len(entries) == 1
        assert entries[0].table_id == "table_id_not_found"
        assert entries[0].table_url == ""
        assert "Table ID not found in href" in caplog.text


class TestParseIodListFromHtml:
    """Tests for Model._parse_iod_list_from_html."""

    def test_raises_value_error_when_list_of_tables_section_missing(self, model):
        """A ValueError is raised when the soup has no div.list-of-tables.

        Includes an empty div.titlepage so dom_parser.get_version (called before the
        list-of-tables check) takes its "titlepage present but no subtitle" branch rather
        than its "no titlepage at all" branch -- the latter currently raises an unrelated
        UnboundLocalError inside dcmspec's own DOMTableSpecParser._version_from_book
        (dcmspec 0.3.1), which is out of scope for this repo's test suite.
        """
        soup = BeautifulSoup('<html><body><div class="titlepage"></div></body></html>', "html.parser")
        with pytest.raises(ValueError, match="list-of-tables"):
            model._parse_iod_list_from_html(soup)

    def test_returns_entries_and_version_for_full_soup(self, model, monkeypatch):
        """A full document soup yields the parsed IOD entries and the detected version."""
        monkeypatch.setattr(model.dom_parser, "get_version", lambda soup, default: "STUBBED_VERSION")
        full_html = f"<html><body>{list_of_tables_soup()}</body></html>"
        soup = BeautifulSoup(full_html, "html.parser")

        entries, version = model._parse_iod_list_from_html(soup)

        assert version == "STUBBED_VERSION"
        assert {e.table_id for e in entries} == {"table_A.2-1", "table_B.7-1", "table_F.3-1"}


class TestDetectVersionChanged:
    """Tests for Model._detect_version_changed."""

    def test_true_when_versions_differ(self, model):
        """A different version than the currently tracked one is reported as changed."""
        model._version = "2025d"
        assert model._detect_version_changed("2026c") is True

    def test_false_when_version_is_the_same(self, model):
        """The same version as currently tracked is not reported as changed."""
        model._version = "2026c"
        assert model._detect_version_changed("2026c") is False

    def test_false_when_no_previous_version_tracked(self, model):
        """No previous version (None) never counts as a change."""
        model._version = None
        assert model._detect_version_changed("2026c") is False


class TestBuildIodsModel:
    """Tests for Model._build_iods_model."""

    def test_keys_entries_by_table_id(self, model):
        """The returned dict is keyed by each entry's table_id."""
        entries = [
            IODEntry("Foo", "table_A.1-1", "http://example.com/a", "Composite"),
            IODEntry("Bar", "table_B.1-1", "http://example.com/b", "Normalized"),
        ]
        result = model._build_iods_model(entries)
        assert result == {"table_A.1-1": entries[0], "table_B.1-1": entries[1]}


class TestGetModuleRefLink:
    """Tests for Model.get_module_ref_link."""

    # Real ref value from cache/model/Part3_table_A.3-1_expanded.json (DICOM PS3.3 2026c) --
    # note the self-closing <a id=.../> sibling before the <a class="xref">, a structure a
    # hand-written snippet would likely miss.
    REAL_REF_VALUE = (
        "<p>\n"
        '<a id="para_4e3e8104-1463-4f8f-822c-d57964e4e66d" shape="rect"/>\n'
        '<a class="xref" href="#sect_C.7.1.1" shape="rect" title="C.7.1.1 Patient Module">C.7.1.1</a>\n'
        "</p>"
    )

    def test_returns_anchor_for_fragment_href(self, model):
        """A real xref anchor with a '#' fragment href is rewritten to a Part3 XHTML link."""
        result = model.get_module_ref_link(self.REAL_REF_VALUE)
        assert result == f'<a href="{model.PART3_XHTML_URL}#sect_C.7.1.1">C.7.1.1</a>'

    def test_escapes_unsafe_non_fragment_href(self, model, caplog):
        """Synthetic XSS case: a non-fragment href is escaped as plain text, not linked."""
        ref_value = '<a class="xref" href="javascript:alert(1)">click</a>'
        with caplog.at_level("WARNING"):
            result = model.get_module_ref_link(ref_value)
        assert "<a " not in result
        assert "javascript:alert(1)" in result  # rendered as plain text, not executable
        assert "Unsafe or unexpected href" in caplog.text

    def test_returns_empty_string_for_falsy_input(self, model):
        """Empty string and None both return an empty string."""
        assert model.get_module_ref_link("") == ""
        assert model.get_module_ref_link(None) == ""

    def test_escapes_when_no_anchor_tag_found(self, model):
        """Plain text with no <a> tag at all falls through to html.escape."""
        result = model.get_module_ref_link("<b>no anchor here</b>")
        assert result == "&lt;b&gt;no anchor here&lt;/b&gt;"


class TestGetSpecmodelNode:
    """Tests for Model.get_specmodel_node against a small in-memory anytree fixture."""

    @pytest.fixture
    def tree_specmodel(self, model):
        """Register a small SpecModel tree (root -> ModuleA -> AttributeB) under table_id "t1"."""
        content = Node("content")
        module = Node("ModuleA", parent=content)
        Node("AttributeB", parent=module)
        specmodel = SpecModel(metadata=Node("metadata"), content=content)
        model._iod_specmodels["t1"] = specmodel
        return specmodel

    def test_empty_relative_path_returns_root_node(self, model, tree_specmodel):
        """An empty relative_path returns the specmodel's content root node."""
        assert model.get_specmodel_node("t1", "") is tree_specmodel.content

    def test_multi_segment_path_walks_nested_children(self, model, tree_specmodel):
        """A multi-segment relative_path walks down matching child node names."""
        node = model.get_specmodel_node("t1", "ModuleA/AttributeB")
        assert node.name == "AttributeB"

    def test_missing_table_id_returns_none(self, model, tree_specmodel):
        """A table_id with no loaded specmodel returns None."""
        assert model.get_specmodel_node("unknown_table_id", "ModuleA") is None

    def test_missing_path_segment_returns_none(self, model, tree_specmodel):
        """A path segment that doesn't match any child name returns None."""
        assert model.get_specmodel_node("t1", "ModuleA/DoesNotExist") is None

    def test_specmodel_missing_content_returns_none(self, model):
        """A loaded specmodel with no content attribute returns None."""
        model._iod_specmodels["t2"] = object()
        assert model.get_specmodel_node("t2", "ModuleA") is None


class TestGetNodePublicAttrs:
    """Tests for Model.get_node_public_attrs."""

    @pytest.fixture
    def tree_specmodel(self, model):
        """Register a small SpecModel tree with a node carrying a plain and an underscore-prefixed attribute.

        "Attribute" here is a Python object attribute on the anytree Node, not a DICOM Attribute
        (Data Element) -- get_node_public_attrs filters by leading underscore, unrelated to DICOM's
        own public/private tag concept.
        """
        content = Node("content")
        module = Node("ModuleA", parent=content)
        module.usage = "M"
        module._internal = "hidden"
        specmodel = SpecModel(metadata=Node("metadata"), content=content)
        model._iod_specmodels["t1"] = specmodel
        return specmodel

    def test_filters_out_underscore_prefixed_attrs(self, model, tree_specmodel):
        """Attributes starting with an underscore (including anytree's own) are excluded."""
        attrs = model.get_node_public_attrs("t1", "ModuleA")
        assert attrs["name"] == "ModuleA"
        assert attrs["usage"] == "M"
        assert all(not k.startswith("_") for k in attrs)

    def test_returns_none_when_node_not_found(self, model, tree_specmodel):
        """No matching node (missing table_id or path) returns None."""
        assert model.get_node_public_attrs("t1", "DoesNotExist") is None


class TestCacheDirHelpers:
    """Tests for the cache-directory path helper methods, all trivial os.path.join wrappers."""

    def test_standard_cache_dir_joins_cache_dir_and_standard(self, model):
        """_standard_cache_dir is cache_dir/standard."""
        assert model._standard_cache_dir() == os.path.join(model.config.cache_dir, "standard")

    def test_model_cache_dir_joins_cache_dir_and_model(self, model):
        """_model_cache_dir is cache_dir/model."""
        assert model._model_cache_dir() == os.path.join(model.config.cache_dir, "model")

    def test_versioned_dir_joins_cache_dir_and_version(self, model):
        """_versioned_dir is cache_dir/<version>."""
        assert model._versioned_dir("2026c") == os.path.join(model.config.cache_dir, "2026c")

    def test_versioned_standard_dir_joins_versioned_dir_and_standard(self, model):
        """_versioned_standard_dir is cache_dir/<version>/standard."""
        assert model._versioned_standard_dir("2026c") == os.path.join(model.config.cache_dir, "2026c", "standard")

    def test_versioned_model_dir_joins_versioned_dir_and_model(self, model):
        """_versioned_model_dir is cache_dir/<version>/model."""
        assert model._versioned_model_dir("2026c") == os.path.join(model.config.cache_dir, "2026c", "model")


class TestMoveFolderIfExists:
    """Tests for Model._move_folder_if_exists."""

    def test_creates_parent_dir_and_moves_when_source_exists(self, model, tmp_path):
        """The source folder is moved to dst, creating ensure_parent's directory first."""
        src = tmp_path / "src_dir"
        src.mkdir()
        (src / "file.txt").write_text("content")
        parent = tmp_path / "nested"
        dst = parent / "dst_dir"

        model._move_folder_if_exists(str(src), str(dst), ensure_parent=str(parent))

        assert not src.exists()
        assert (dst / "file.txt").read_text() == "content"

    def test_noop_when_source_missing(self, model, tmp_path):
        """Nothing is moved or created when the source folder doesn't exist."""
        src = tmp_path / "does_not_exist"
        dst = tmp_path / "dst_dir"

        model._move_folder_if_exists(str(src), str(dst))

        assert not dst.exists()

    def test_move_failure_logs_warning_without_propagating(self, model, tmp_path, monkeypatch, caplog):
        """A shutil.move failure is caught, logged as a warning, and not raised."""
        src = tmp_path / "src_dir"
        src.mkdir()
        dst = tmp_path / "dst_dir"

        def _raise_os_error(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("shutil.move", _raise_os_error)

        with caplog.at_level("WARNING"):
            model._move_folder_if_exists(str(src), str(dst))

        assert "Failed to move" in caplog.text


class TestTempFileHelpers:
    """Tests for the temp-file helpers used by Model.load_iod_list's force_download path."""

    def test_create_temp_iod_list_file_creates_html_file_under_standard_cache_dir(self, model):
        """A unique .html temp file is created under _standard_cache_dir()."""
        os.makedirs(model._standard_cache_dir(), exist_ok=True)

        temp_file_name, temp_file_path = model._create_temp_iod_list_file()

        assert os.path.exists(temp_file_path)
        assert temp_file_path == os.path.join(model._standard_cache_dir(), temp_file_name)
        assert temp_file_name.endswith(".html")

    def test_move_temp_file_to_cache_root_moves_and_returns_new_path(self, model):
        """The temp file is moved from cache/standard to the cache root, returning the new path."""
        os.makedirs(model._standard_cache_dir(), exist_ok=True)
        temp_file_name, temp_file_path = model._create_temp_iod_list_file()

        new_path = model._move_temp_file_to_cache_root(temp_file_name)

        assert new_path == os.path.join(model.config.cache_dir, temp_file_name)
        assert os.path.exists(new_path)
        assert not os.path.exists(temp_file_path)

    def test_move_temp_file_to_cache_root_failure_returns_original_path_and_logs_warning(
        self, model, monkeypatch, caplog
    ):
        """On a shutil.move failure, the original cache/standard path is returned and a warning is logged."""
        os.makedirs(model._standard_cache_dir(), exist_ok=True)
        temp_file_name, temp_file_path = model._create_temp_iod_list_file()

        def _raise_os_error(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("shutil.move", _raise_os_error)

        with caplog.at_level("WARNING"):
            result = model._move_temp_file_to_cache_root(temp_file_name)

        assert result == temp_file_path
        assert "Failed to move" in caplog.text

    def test_move_temp_iod_list_to_cache_creates_dest_dir_if_missing_and_moves(self, model, tmp_path):
        """The temp file is moved into cache/standard/<cache_file_name>, creating the dir if missing."""
        temp_file_path = tmp_path / "downloaded.html"
        temp_file_path.write_text("downloaded content")

        model._move_temp_iod_list_to_cache(str(temp_file_path), "ps3.3.html")

        dest = os.path.join(model._standard_cache_dir(), "ps3.3.html")
        assert os.path.exists(dest)
        with open(dest, encoding="utf-8") as f:
            assert f.read() == "downloaded content"
        assert not temp_file_path.exists()

    def test_move_temp_iod_list_to_cache_failure_logs_warning_without_propagating(
        self, model, tmp_path, monkeypatch, caplog
    ):
        """A shutil.move failure is caught, logged as a warning, and not raised."""
        temp_file_path = tmp_path / "downloaded.html"
        temp_file_path.write_text("downloaded content")

        def _raise_os_error(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("shutil.move", _raise_os_error)

        with caplog.at_level("WARNING"):
            model._move_temp_iod_list_to_cache(str(temp_file_path), "ps3.3.html")

        assert "Failed to move" in caplog.text
