"""Unit tests for dcmspec_explorer.services.iod_export_service.IODExportWorker."""

import queue

import pytest
from anytree import Node

from dcmspec_explorer.services.iod_export_service import IODExportWorker


def _chained_runtime_error():
    """Return a RuntimeError chained onto a ValueError, as if raised via `raise ... from ...`."""
    try:
        raise RuntimeError("wrapped") from ValueError("inner")
    except RuntimeError as error:
        return error


class FakeIodModel:
    """Fake loaded IOD spec model exposing only the .content attribute the worker needs."""

    def __init__(self, content):
        """Initialize with the given anytree content root."""
        self.content = content


def _make_iod_model(elem_description="<p>Patient's full name.</p>"):
    """Build a minimal fake IOD model: one module with one attribute carrying an HTML description."""
    content = Node("content")
    module = Node("PatientModule", parent=content)
    module.module = "Patient"
    attr_node = Node("attr", parent=module)
    attr_node.elem_name = "Patient's Name"
    attr_node.elem_description = elem_description
    return FakeIodModel(content)


def _find_attr_node(content):
    """Return the single attribute node (grandchild of content) in a model built by _make_iod_model."""
    return content.children[0].children[0]


class FakePrinter:
    """Fake IODSpecPrinter recording which print method was called, or raising a canned error."""

    instances: list["FakePrinter"] = []

    def __init__(self, model, logger=None, output=None, error=None):
        """Record the construction args and register self in the class-level instances list."""
        self.model = model
        self.logger = logger
        self.output = output
        self.error = error
        self.print_csv_calls = 0
        self.print_xlsx_calls = 0
        FakePrinter.instances.append(self)

    def print_csv(self):
        """Record the call, or raise the canned error."""
        self.print_csv_calls += 1
        if self.error is not None:
            raise self.error

    def print_xlsx(self):
        """Record the call, or raise the canned error."""
        self.print_xlsx_calls += 1
        if self.error is not None:
            raise self.error


@pytest.fixture(autouse=True)
def _reset_fake_printer_instances():
    """Clear FakePrinter.instances before each test."""
    FakePrinter.instances.clear()


def _patch_printer(monkeypatch, error=None):
    """Monkeypatch IODExportWorker's IODSpecPrinter import to FakePrinter, optionally raising error."""
    import dcmspec_explorer.services.iod_export_service as iod_export_service_module

    def factory(model, logger=None, output=None):
        return FakePrinter(model, logger=logger, output=output, error=error)

    monkeypatch.setattr(iod_export_service_module, "IODSpecPrinter", factory)


class TestIODExportWorker:
    """Tests for IODExportWorker.run."""

    def test_csv_export_calls_print_csv_and_puts_loaded_event(self, fake_logger, monkeypatch):
        """A "csv" export constructs the printer with the right args and calls print_csv."""
        _patch_printer(monkeypatch)
        event_queue = queue.Queue()
        iod_model = _make_iod_model()
        worker = IODExportWorker(
            iod_model=iod_model,
            fmt="csv",
            output_path="/tmp/out.csv",
            logger=fake_logger,
            event_queue=event_queue,
        )

        worker.run()

        assert event_queue.get_nowait() == ("loaded", "/tmp/out.csv")
        printer = FakePrinter.instances[0]
        assert printer.logger is fake_logger
        assert printer.output == "/tmp/out.csv"
        assert printer.print_csv_calls == 1
        assert printer.print_xlsx_calls == 0

    def test_xlsx_export_calls_print_xlsx_and_puts_loaded_event(self, fake_logger, monkeypatch):
        """An "xlsx" export constructs the printer with the right args and calls print_xlsx."""
        _patch_printer(monkeypatch)
        event_queue = queue.Queue()
        worker = IODExportWorker(
            iod_model=_make_iod_model(),
            fmt="xlsx",
            output_path="/tmp/out.xlsx",
            logger=fake_logger,
            event_queue=event_queue,
        )

        worker.run()

        assert event_queue.get_nowait() == ("loaded", "/tmp/out.xlsx")
        printer = FakePrinter.instances[0]
        assert printer.print_xlsx_calls == 1
        assert printer.print_csv_calls == 0

    def test_unsupported_format_puts_error_event(self, fake_logger, monkeypatch):
        """An unrecognized fmt puts an error event instead of calling any print method."""
        _patch_printer(monkeypatch)
        event_queue = queue.Queue()
        worker = IODExportWorker(
            iod_model=_make_iod_model(),
            fmt="pdf",
            output_path="/tmp/out.pdf",
            logger=fake_logger,
            event_queue=event_queue,
        )

        worker.run()

        assert event_queue.get_nowait() == ("error", "Unsupported export format: pdf")
        assert FakePrinter.instances[0].print_csv_calls == 0
        assert FakePrinter.instances[0].print_xlsx_calls == 0

    def test_printer_exception_puts_error_event(self, fake_logger, monkeypatch):
        """When the printer raises, ("error", <message>) is put on the queue instead."""
        _patch_printer(monkeypatch, error=RuntimeError("disk full"))
        event_queue = queue.Queue()
        worker = IODExportWorker(
            iod_model=_make_iod_model(),
            fmt="csv",
            output_path="/tmp/out.csv",
            logger=fake_logger,
            event_queue=event_queue,
        )

        worker.run()

        assert event_queue.get_nowait() == ("error", "disk full")

    def test_chained_exception_only_queues_the_outer_message_but_logs_the_full_chain(
        self, fake_logger, caplog, monkeypatch
    ):
        """A chained exception's cause/traceback are dropped from the queued message, but logged in full."""
        _patch_printer(monkeypatch, error=_chained_runtime_error())
        event_queue = queue.Queue()
        worker = IODExportWorker(
            iod_model=_make_iod_model(),
            fmt="csv",
            output_path="/tmp/out.csv",
            logger=fake_logger,
            event_queue=event_queue,
        )

        worker.run()

        assert event_queue.get_nowait() == ("error", "wrapped")
        assert caplog.records[-1].levelname == "ERROR"
        assert "ValueError" in caplog.text
        assert "inner" in caplog.text


class TestToPlainTextModel:
    """Tests for IODExportWorker._to_plain_text_model."""

    def test_converts_html_description_to_plain_text(self):
        """An HTML elem_description is converted to plain text on the returned copy."""
        iod_model = _make_iod_model(elem_description="<p>Patient's <b>full</b> name.</p>")

        export_model = IODExportWorker._to_plain_text_model(iod_model)

        assert _find_attr_node(export_model.content).elem_description == "Patient's full name."

    def test_does_not_mutate_the_original_model(self):
        """The original model's HTML description is left untouched."""
        original_html = "<p>Patient's <b>full</b> name.</p>"
        iod_model = _make_iod_model(elem_description=original_html)

        IODExportWorker._to_plain_text_model(iod_model)

        assert _find_attr_node(iod_model.content).elem_description == original_html

    def test_leaves_other_attributes_untouched(self):
        """Attributes other than the known HTML-flagged ones pass through unchanged."""
        iod_model = _make_iod_model()

        export_model = IODExportWorker._to_plain_text_model(iod_model)

        assert _find_attr_node(export_model.content).elem_name == "Patient's Name"

    def test_missing_html_attr_does_not_raise(self):
        """A node without any of the known HTML-flagged attributes is left alone without error."""
        content = Node("content")
        module = Node("PatientModule", parent=content)
        module.module = "Patient"
        iod_model = FakeIodModel(content)

        export_model = IODExportWorker._to_plain_text_model(iod_model)  # must not raise

        assert export_model.content.children[0].module == "Patient"


class TestHtmlToText:
    """Tests for IODExportWorker._html_to_text."""

    def test_strips_tags_and_extracts_readable_text(self):
        """Anchors and other markup collapse into their plain-text content."""
        html = '<p>\n<a id="para_427a23ce" shape="rect"/>Patient\'s full name.</p>'
        assert IODExportWorker._html_to_text(html) == "Patient's full name."

    def test_note_div_content_is_preserved_on_its_own_paragraph(self):
        """A nested <div class="note">'s heading and paragraph become blank-line-separated blocks."""
        html = (
            "<p>Primary identifier for the Patient.</p>"
            '<div class="note"><h3 class="title">Note</h3>'
            '<p>See <a href="#sect">Section C.7.1.4.1.1</a>.</p></div>'
        )
        assert IODExportWorker._html_to_text(html) == (
            "Primary identifier for the Patient.\n\nNote\n\nSee Section C.7.1.4.1.1."
        )

    def test_definition_list_terms_are_not_dropped(self):
        """A <dl>/<dt>/<dd> enumerated-values list (e.g. Patient's Sex) keeps every term and value.

        Regression test: an earlier hand-rolled BeautifulSoup-based extraction silently dropped
        <dt> content because it wasn't in its block-tag whitelist. inscriptis renders the full DOM
        instead of relying on a tag whitelist, so nothing is silently lost.
        """
        html = (
            "<p>Sex of the named Patient.</p>"
            '<div class="variablelist"><p class="title"><strong>Enumerated Values:</strong></p>'
            '<dl class="variablelist compact">'
            '<dt><span class="term">M</span></dt><dd><p>male</p></dd>'
            '<dt><span class="term">F</span></dt><dd><p>female</p></dd>'
            "</dl></div>"
            "<p>See Note 2 and Note 3.</p>"
        )
        text = IODExportWorker._html_to_text(html)
        expected_fragments = ("Sex of the named Patient.", "M", "male", "F", "female", "See Note 2 and Note 3.")
        assert all(fragment in text for fragment in expected_fragments)

    def test_no_markdown_syntax_leaks_through(self):
        """Headings, blockquotes, code spans, and horizontal rules produce no Markdown syntax."""
        html = (
            '<p>See <a href="#x">link</a> and <strong>bold</strong> and <code>code</code> and:</p>'
            "<blockquote>a quote</blockquote>"
            "<hr/>"
            "<h3>Note</h3>"
        )
        text = IODExportWorker._html_to_text(html)
        assert all(markdown_char not in text for markdown_char in ("#", ">", "`", "---"))

    def test_no_markup_is_returned_as_is(self):
        """Plain text with no HTML markup passes through unchanged (aside from stripping)."""
        assert IODExportWorker._html_to_text("Just plain text.") == "Just plain text."
