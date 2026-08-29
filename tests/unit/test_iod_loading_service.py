"""Unit tests for dcmspec_explorer.services.iod_loading_service loader workers."""

import queue

from dcmspec_explorer.services.iod_loading_service import IODListLoaderWorker, IODModelLoaderWorker
from dcmspec_explorer.services.progress_observer import ServiceProgressObserver


def _chained_runtime_error():
    """Return a RuntimeError chained onto a ValueError, as if raised via `raise ... from ...`."""
    try:
        raise RuntimeError("wrapped") from ValueError("inner")
    except RuntimeError as error:
        return error


class FakeModel:
    """Fake model recording calls and returning or raising a canned result."""

    def __init__(self, iod_list=None, iod_model=None, error=None):
        """Initialize the fake with the value or exception each load method should produce."""
        self.iod_list = iod_list
        self.iod_model = iod_model
        self.error = error
        self.load_iod_list_calls = []
        self.load_iod_model_calls = []

    def load_iod_list(self, force_download, progress_observer):
        """Record the call and return iod_list, or raise the canned error."""
        self.load_iod_list_calls.append((force_download, progress_observer))
        return self._result(self.iod_list)

    def load_iod_model(self, table_id, logger, progress_observer):
        """Record the call and return iod_model, or raise the canned error."""
        self.load_iod_model_calls.append((table_id, logger, progress_observer))
        return self._result(self.iod_model)

    def _result(self, value):
        """Raise the canned error if set, otherwise return the given value."""
        if self.error is not None:
            raise self.error
        return value


class TestIODListLoaderWorker:
    """Tests for IODListLoaderWorker.run."""

    def test_success_puts_loaded_event_and_calls_model_with_right_args(self, fake_logger):
        """On success, ("loaded", <list>) is queued and load_iod_list is called with the right args."""
        event_queue = queue.Queue()
        model = FakeModel(iod_list=["entry1", "entry2"])
        worker = IODListLoaderWorker(model=model, logger=fake_logger, event_queue=event_queue, force_download=True)

        worker.run()

        assert event_queue.get_nowait() == ("loaded", ["entry1", "entry2"])
        assert len(model.load_iod_list_calls) == 1
        force_download, progress_observer = model.load_iod_list_calls[0]
        assert force_download is True
        assert isinstance(progress_observer, ServiceProgressObserver)
        assert progress_observer.event_queue is event_queue

    def test_exception_puts_error_event(self, fake_logger):
        """When load_iod_list raises, ("error", <message>) is put on the queue instead."""
        event_queue = queue.Queue()
        model = FakeModel(error=RuntimeError("boom"))
        worker = IODListLoaderWorker(model=model, logger=fake_logger, event_queue=event_queue)

        worker.run()

        assert event_queue.get_nowait() == ("error", "boom")

    def test_chained_exception_only_queues_the_outer_message_but_logs_the_full_chain(self, fake_logger, caplog):
        """A chained exception's cause/traceback are dropped from the queued message, but logged in full."""
        event_queue = queue.Queue()
        model = FakeModel(error=_chained_runtime_error())
        worker = IODListLoaderWorker(model=model, logger=fake_logger, event_queue=event_queue)

        worker.run()

        assert event_queue.get_nowait() == ("error", "wrapped")
        assert caplog.records[-1].levelname == "ERROR"
        assert "ValueError" in caplog.text
        assert "inner" in caplog.text


class TestIODModelLoaderWorker:
    """Tests for IODModelLoaderWorker.run."""

    def test_success_puts_loaded_event_and_calls_model_with_right_args(self, fake_logger):
        """On success, ("loaded", <model>) is queued and load_iod_model is called with the right args."""
        event_queue = queue.Queue()
        model = FakeModel(iod_model="some_spec_model")
        worker = IODModelLoaderWorker(model=model, table_id="table_A.2-1", logger=fake_logger, event_queue=event_queue)

        worker.run()

        assert event_queue.get_nowait() == ("loaded", "some_spec_model")
        assert len(model.load_iod_model_calls) == 1
        table_id, logger, progress_observer = model.load_iod_model_calls[0]
        assert table_id == "table_A.2-1"
        assert logger is fake_logger
        assert isinstance(progress_observer, ServiceProgressObserver)
        assert progress_observer.event_queue is event_queue

    def test_exception_puts_error_event(self, fake_logger):
        """When load_iod_model raises, ("error", <message>) is put on the queue instead."""
        event_queue = queue.Queue()
        model = FakeModel(error=ValueError("bad table_id"))
        worker = IODModelLoaderWorker(model=model, table_id="table_A.2-1", logger=fake_logger, event_queue=event_queue)

        worker.run()

        assert event_queue.get_nowait() == ("error", "bad table_id")

    def test_chained_exception_only_queues_the_outer_message_but_logs_the_full_chain(self, fake_logger, caplog):
        """A chained exception's cause/traceback are dropped from the queued message, but logged in full."""
        event_queue = queue.Queue()
        model = FakeModel(error=_chained_runtime_error())
        worker = IODModelLoaderWorker(model=model, table_id="table_A.2-1", logger=fake_logger, event_queue=event_queue)

        worker.run()

        assert event_queue.get_nowait() == ("error", "wrapped")
        assert caplog.records[-1].levelname == "ERROR"
        assert "ValueError" in caplog.text
        assert "inner" in caplog.text
