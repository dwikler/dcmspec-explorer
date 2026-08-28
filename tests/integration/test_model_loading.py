"""Integration tests for Model.load_iod_list / load_iod_model, mocking only the network boundary.

Model has no constructor option to swap in a fake doc handler or spec builder, so instead
of a real network call, these tests replace the specific method that would make one:
model.doc_handler.load_document (for load_iod_list) and
dcmspec_explorer.model.model.IODSpecBuilder.build_from_url (for load_iod_model). This
mirrors how dcmspec's own test suite handles the same problem.
"""

import os

import pytest
from anytree import Node
from bs4 import BeautifulSoup
from dcmspec.spec_model import SpecModel

from dcmspec_explorer.model.model import Model

from ..unit.fixtures_iod_list import list_of_tables_soup


@pytest.fixture
def model(make_config, fake_logger):
    """Return a Model instance backed by a real, tmp_path-isolated Config."""
    return Model(config=make_config(), logger=fake_logger)


@pytest.fixture
def full_soup():
    """Wrap the real list-of-tables excerpt fixture in a full HTML document.

    Includes an empty <div class="titlepage"> to work around a dcmspec 0.3.1 bug
    (dwikler/dcmspec#119) where DOMTableSpecParser._version_from_book raises
    UnboundLocalError when no titlepage div is present at all -- dom_parser.get_version is
    also monkeypatched below in every test that needs a specific version string, so the
    titlepage content itself doesn't matter.
    """
    html = f'<html><body><div class="titlepage"></div>{list_of_tables_soup()}</body></html>'
    return BeautifulSoup(html, "html.parser")


def _make_specmodel():
    return SpecModel(metadata=Node("metadata"), content=Node("content"))


class TestLoadIodList:
    """Tests for Model.load_iod_list."""

    def test_success_updates_version_and_iod_list(self, model, monkeypatch, full_soup):
        """A successful load updates model.version and model.iod_list from the parsed soup."""
        monkeypatch.setattr(model.doc_handler, "load_document", lambda **kwargs: full_soup)
        monkeypatch.setattr(model.dom_parser, "get_version", lambda soup, default: "2026c")

        entries = model.load_iod_list(force_download=False)

        assert model.version == "2026c"
        assert len(model.iod_list) == len(entries)
        assert {e.table_id for e in entries} == {"table_A.2-1", "table_B.7-1", "table_F.3-1"}

    def test_doc_handler_exception_is_wrapped_as_runtime_error(self, model, monkeypatch):
        """An exception from doc_handler.load_document is wrapped in a RuntimeError with the original as cause."""
        original_error = ConnectionError("network unreachable")

        def raise_error(**kwargs):
            raise original_error

        monkeypatch.setattr(model.doc_handler, "load_document", raise_error)

        with pytest.raises(RuntimeError) as exc_info:
            model.load_iod_list(force_download=False)

        assert exc_info.value.__cause__ is original_error

    def test_force_download_with_version_change_archives_cache_and_clears_specmodels(
        self, model, monkeypatch, full_soup
    ):
        """A version change on force_download archives the old cache and clears in-memory specmodels."""
        model._version = "2025d"
        model._iod_specmodels["table_A.2-1"] = _make_specmodel()

        standard_dir = model._standard_cache_dir()
        os.makedirs(standard_dir, exist_ok=True)
        old_content = "<html>old 2025d cache</html>"
        with open(os.path.join(standard_dir, "ps3.3.html"), "w", encoding="utf-8") as f:
            f.write(old_content)

        monkeypatch.setattr(model.doc_handler, "load_document", lambda **kwargs: full_soup)
        monkeypatch.setattr(model.dom_parser, "get_version", lambda soup, default: "2026c")

        model.load_iod_list(force_download=True)

        assert model.version == "2026c"
        assert model._iod_specmodels == {}
        # The old cache content was moved into the versioned archive, not left in place or discarded.
        archived_file = os.path.join(model._versioned_standard_dir("2025d"), "ps3.3.html")
        with open(archived_file, encoding="utf-8") as f:
            assert f.read() == old_content


class TestLoadIodModel:
    """Tests for Model.load_iod_model."""

    def test_returns_in_memory_cached_instance_without_calling_build_from_url(self, model, monkeypatch, fake_logger):
        """An already-loaded table_id is returned from memory without invoking IODSpecBuilder.build_from_url."""
        cached = _make_specmodel()
        model._iod_specmodels["table_A.2-1"] = cached

        def fail_if_called(self, **kwargs):
            raise AssertionError("build_from_url should not be called for an already-cached table_id")

        monkeypatch.setattr("dcmspec_explorer.model.model.IODSpecBuilder.build_from_url", fail_if_called)

        result = model.load_iod_model("table_A.2-1", fake_logger)

        assert result is cached

    def test_success_stores_and_returns_the_built_specmodel(self, model, monkeypatch, fake_logger):
        """A successful build stores the returned SpecModel in memory and returns it."""
        built = _make_specmodel()
        monkeypatch.setattr(
            "dcmspec_explorer.model.model.IODSpecBuilder.build_from_url",
            lambda self, **kwargs: (built, None),
        )

        result = model.load_iod_model("table_A.2-1", fake_logger)

        assert result is built
        assert model.iod_specmodels["table_A.2-1"] is built

    def test_value_error_unpacking_result_is_wrapped_as_runtime_error(self, model, monkeypatch, fake_logger):
        """A ValueError unpacking build_from_url's return value is wrapped as a RuntimeError."""
        original_error = ValueError("not enough values to unpack")

        def raise_error(self, **kwargs):
            raise original_error

        monkeypatch.setattr("dcmspec_explorer.model.model.IODSpecBuilder.build_from_url", raise_error)

        with pytest.raises(RuntimeError) as exc_info:
            model.load_iod_model("table_A.2-1", fake_logger)

        assert exc_info.value.__cause__ is original_error

    def test_non_specmodel_return_raises_type_error(self, model, monkeypatch, fake_logger):
        """A build_from_url return value that isn't a SpecModel raises a TypeError."""
        monkeypatch.setattr(
            "dcmspec_explorer.model.model.IODSpecBuilder.build_from_url",
            lambda self, **kwargs: ("not a SpecModel", None),
        )

        with pytest.raises(TypeError):
            model.load_iod_model("table_A.2-1", fake_logger)

    def test_specmodel_missing_content_raises_runtime_error(self, model, monkeypatch, fake_logger):
        """A SpecModel returned without a content attribute raises a RuntimeError."""
        built = _make_specmodel()
        del built.content
        monkeypatch.setattr(
            "dcmspec_explorer.model.model.IODSpecBuilder.build_from_url",
            lambda self, **kwargs: (built, None),
        )

        with pytest.raises(RuntimeError):
            model.load_iod_model("table_A.2-1", fake_logger)

    @pytest.mark.parametrize(
        "table_id, expected_mapping",
        [
            ("table_A.2-1", {0: "ie", 1: "module", 2: "ref", 3: "usage"}),
            ("table_B.7-1", {0: "module", 1: "ref", 2: "description"}),
        ],
    )
    def test_selects_composite_or_normalized_column_mapping(
        self, model, monkeypatch, fake_logger, table_id, expected_mapping
    ):
        """The IOD SpecFactory's column_to_attr mapping matches composite vs normalized IOD kind."""
        factory_calls = []

        class FakeSpecFactory:
            def __init__(self, **kwargs):
                factory_calls.append(kwargs)

        built = _make_specmodel()
        monkeypatch.setattr("dcmspec_explorer.model.model.SpecFactory", FakeSpecFactory)
        monkeypatch.setattr(
            "dcmspec_explorer.model.model.IODSpecBuilder.build_from_url",
            lambda self, **kwargs: (built, None),
        )

        model.load_iod_model(table_id, fake_logger)

        iod_factory_call = factory_calls[0]
        assert iod_factory_call["column_to_attr"] == expected_mapping
