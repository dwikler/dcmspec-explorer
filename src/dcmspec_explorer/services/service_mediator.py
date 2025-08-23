"""Mediator between service layer and controller of DCM Spec Explorer."""

import queue
from typing import Any, Optional, Tuple
import threading

from PySide6.QtCore import QObject, Signal, QTimer

from dcmspec.progress import Progress

from dcmspec_explorer.services.iod_loading_service import IODListLoaderWorker
from dcmspec_explorer.services.iod_loading_service import IODModelLoaderWorker


class BaseServiceMediator(QObject):
    """Manage background worker lifecycle and event-to-signal dispatch for service mediators.

    This base class handles starting a background worker in a thread, polling its event queue,
    and emitting Qt signals mapped to worker events.
    Subclasses must define a `_signal_map` attribute mapping event type strings
    (e.g., 'progress','loaded', 'error') to tuples of (Qt Signal, boolean),
    where the boolean indicates whether to perform cleanup after handling that event.
    Call `start_worker(worker_cls, *worker_args)` to launch the worker.

    Args:
        model: The data model instance to be used by the worker.
        logger: Logger instance for logging progress and errors.
        parent: Optional QObject parent for proper Qt object ownership.

    Example usage in a subclass:
        self._signal_map = {
            "progress": (self.progress_signal, False),
            "loaded": (self.loaded_signal, True),
            "error": (self.error_signal, True),
        }
        self.start_worker(MyWorkerClass, arg1, arg2)

    """

    def __init__(self, model: Any, logger: Any, parent: Optional[QObject] = None) -> None:
        """Initialize the service mediator.

        Args:
            model: The data model instance to be used by the worker.
            logger: Logger instance for logging progress and errors.
            parent: Optional QObject parent for proper Qt object ownership.

        """
        super().__init__(parent)
        self.model = model
        self.logger = logger

        self._event_queue = None
        self._worker = None
        self._thread = None
        self._poll_timer = None

    def start_worker(self, worker_cls: type, *worker_args: Any) -> Tuple[Any, threading.Thread]:
        """Start the given worker in a background thread and begin polling its event queue."""
        self._event_queue = queue.Queue()
        self._worker = worker_cls(*worker_args, logger=self.logger, event_queue=self._event_queue)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._thread.start()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_event_queue)
        self._poll_timer.start(50)
        return self._worker, self._thread

    def _poll_event_queue(self) -> None:
        """Poll the event queue for worker events and emit mapped Qt signals."""
        while self._event_queue and not self._event_queue.empty():
            event_type, data = self._event_queue.get()
            signal_tuple = self._signal_map.get(event_type)
            if signal_tuple:
                signal, should_cleanup = signal_tuple
                signal.emit(self, data)
                if should_cleanup:
                    self.cleanup_worker_thread()
                    self._poll_timer.stop()

    def cleanup_worker_thread(self) -> None:
        """Clean up the worker and its thread after completion or error."""
        try:
            if self._thread is not None and self._thread.is_alive() and threading.current_thread() is not self._thread:
                self._thread.join(timeout=1)
            del self._worker
            del self._thread
            self.logger.debug("Worker and thread cleaned up successfully.")
        except Exception as e:
            self.logger.error(f"Error during worker/thread cleanup: {e}", exc_info=True)


class IODListLoaderServiceMediator(BaseServiceMediator):
    """Mediator for IODListLoaderWorker, bridges service worker and Qt signals."""

    # Define Qt Signals with data/payload types
    iodlist_progress_signal = Signal(object, Progress)
    iodlist_loaded_signal = Signal(object, object)
    iodlist_error_signal = Signal(object, str)

    def __init__(self, model: Any, logger: Any, parent: Optional[QObject] = None) -> None:
        """Initialize the IODListLoaderServiceMediator."""
        super().__init__(model, logger, parent)
        self._signal_map = {
            "progress": (self.iodlist_progress_signal, False),
            "loaded": (self.iodlist_loaded_signal, True),
            "error": (self.iodlist_error_signal, True),
        }

    def start_iodlist_worker(self) -> Tuple[IODListLoaderWorker, threading.Thread]:
        """Start the IOD list loader worker in a background thread."""
        return self.start_worker(IODListLoaderWorker, self.model)


class IODModelLoaderServiceMediator(BaseServiceMediator):
    """Mediator for IODModelLoaderWorker, bridges service worker and Qt signals."""

    # Define Qt Signals with data/payload types
    iodmodel_progress_signal = Signal(object, Progress)
    iodmodel_loaded_signal = Signal(object, object)
    iodmodel_error_signal = Signal(object, str)

    def __init__(self, model: Any, logger: Any, parent: Optional[QObject] = None) -> None:
        """Initialize the IODModelLoaderServiceMediator."""
        super().__init__(model, logger, parent)
        self._signal_map = {
            "progress": (self.iodmodel_progress_signal, False),
            "loaded": (self.iodmodel_loaded_signal, True),
            "error": (self.iodmodel_error_signal, True),
        }

    def start_iodmodel_worker(self, table_id: str) -> Tuple[IODModelLoaderWorker, threading.Thread]:
        """Start the IOD model loader worker in a background thread."""
        return self.start_worker(IODModelLoaderWorker, self.model, table_id)
