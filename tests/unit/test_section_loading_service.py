"""Unit tests for dcmspec_explorer.services.section_loading_service.SectionLoaderWorker."""

import queue

from dcmspec_explorer.services.section_loading_service import SectionLoaderWorker


def _chained_runtime_error():
    """Return a RuntimeError chained onto a ValueError, as if raised via `raise ... from ...`."""
    try:
        raise RuntimeError("wrapped") from ValueError("inner")
    except RuntimeError as error:
        return error


class FakeModel:
    """Fake model recording calls and returning or raising a canned result."""

    def __init__(self, section_model=None, error=None):
        """Initialize the fake with the value or exception get_or_load_section should produce."""
        self.section_model = section_model
        self.error = error
        self.get_or_load_section_calls = []

    def get_or_load_section(self, section_id, logger):
        """Record the call and return section_model, or raise the canned error."""
        self.get_or_load_section_calls.append((section_id, logger))
        if self.error is not None:
            raise self.error
        return self.section_model


class TestSectionLoaderWorker:
    """Tests for SectionLoaderWorker.run."""

    def test_success_puts_loaded_event_and_calls_model_with_right_args(self, fake_logger):
        """On success, ("loaded", <model>) is queued and get_or_load_section is called with the right args."""
        event_queue = queue.Queue()
        model = FakeModel(section_model="some_section_model")
        worker = SectionLoaderWorker(
            model=model, section_id="sect_C.7.6.16.2.1.1", logger=fake_logger, event_queue=event_queue
        )

        worker.run()

        assert event_queue.get_nowait() == ("loaded", "some_section_model")
        assert model.get_or_load_section_calls == [("sect_C.7.6.16.2.1.1", fake_logger)]

    def test_exception_puts_error_event(self, fake_logger):
        """When get_or_load_section raises, ("error", <message>) is put on the queue instead."""
        event_queue = queue.Queue()
        model = FakeModel(error=RuntimeError("boom"))
        worker = SectionLoaderWorker(
            model=model, section_id="sect_C.7.6.16.2.1.1", logger=fake_logger, event_queue=event_queue
        )

        worker.run()

        assert event_queue.get_nowait() == ("error", "boom")

    def test_chained_exception_only_queues_the_outer_message_but_logs_the_full_chain(self, fake_logger, caplog):
        """A chained exception's cause/traceback are dropped from the queued message, but logged in full."""
        event_queue = queue.Queue()
        model = FakeModel(error=_chained_runtime_error())
        worker = SectionLoaderWorker(
            model=model, section_id="sect_C.7.6.16.2.1.1", logger=fake_logger, event_queue=event_queue
        )

        worker.run()

        assert event_queue.get_nowait() == ("error", "wrapped")
        assert caplog.records[-1].levelname == "ERROR"
        assert "ValueError" in caplog.text
        assert "inner" in caplog.text
