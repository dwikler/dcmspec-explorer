"""Unit tests for dcmspec_explorer.services.iod_export_service.IODExportWorker."""

import queue

import pytest

from dcmspec_explorer.services.iod_export_service import IODExportWorker


def _chained_runtime_error():
    """Return a RuntimeError chained onto a ValueError, as if raised via `raise ... from ...`."""
    try:
        raise RuntimeError("wrapped") from ValueError("inner")
    except RuntimeError as error:
        return error


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
        worker = IODExportWorker(
            iod_model="some_spec_model",
            fmt="csv",
            output_path="/tmp/out.csv",
            logger=fake_logger,
            event_queue=event_queue,
        )

        worker.run()

        assert event_queue.get_nowait() == ("loaded", "/tmp/out.csv")
        printer = FakePrinter.instances[0]
        assert printer.model == "some_spec_model"
        assert printer.logger is fake_logger
        assert printer.output == "/tmp/out.csv"
        assert printer.print_csv_calls == 1
        assert printer.print_xlsx_calls == 0

    def test_xlsx_export_calls_print_xlsx_and_puts_loaded_event(self, fake_logger, monkeypatch):
        """An "xlsx" export constructs the printer with the right args and calls print_xlsx."""
        _patch_printer(monkeypatch)
        event_queue = queue.Queue()
        worker = IODExportWorker(
            iod_model="some_spec_model",
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
            iod_model="some_spec_model",
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
            iod_model="some_spec_model",
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
            iod_model="some_spec_model",
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
