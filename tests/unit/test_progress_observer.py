"""Unit tests for dcmspec_explorer.services.progress_observer.ServiceProgressObserver."""

import queue

from dcmspec.progress import Progress, ProgressStatus

from dcmspec_explorer.services.progress_observer import ServiceProgressObserver


class TestCall:
    """Tests for ServiceProgressObserver.__call__."""

    def test_puts_progress_tuple_on_the_event_queue(self):
        """Calling the observer with a Progress instance puts ("progress", <value>) on its queue."""
        event_queue = queue.Queue()
        observer = ServiceProgressObserver(event_queue)
        progress = Progress(percent=50, status=ProgressStatus.DOWNLOADING)

        observer(progress)

        event_type, value = event_queue.get_nowait()
        assert event_type == "progress"
        assert value is progress
