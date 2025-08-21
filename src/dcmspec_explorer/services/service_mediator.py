"""Mediator between service layer and controller of DCM Spec Explorer."""

import queue
from typing import Any, Optional, Tuple
import threading

from PySide6.QtCore import QObject, Signal, QTimer

from dcmspec.progress import Progress

from dcmspec_explorer.services.iod_loading_service import IODListLoaderWorker
from dcmspec_explorer.services.iod_loading_service import IODModelLoaderWorker


class BaseServiceMediator(QObject):
    """Base mediator for service workers, providing common threading and cleanup logic.

    This class provides shared logic for managing worker threads and cleanup. Subclasses should
    implement worker-specific signal translation and startup logic.
    """

    def __init__(self, model: Any, logger: Any, parent: Optional[QObject] = None) -> None:
        """Initialize the service mediator with the model and logger."""
        # Initialize the base class with the app_controller as parent so it is not garbage collected
        super().__init__(parent)
        self.model = model
        self.logger = logger

        # Initialize worker and thread to None
        self._worker = None
        self._thread = None

    def cleanup_worker_thread(self) -> None:
        """Clean up the worker and its thread after completion or error.

        Ensures the worker thread is properly joined and resources are released.
        """
        try:
            if self._thread is not None and self._thread.is_alive() and threading.current_thread() is not self._thread:
                self._thread.join(timeout=1)
            del self._worker
            del self._thread
            self.logger.debug("Worker and thread cleaned up successfully.")
        except Exception as e:
            self.logger.error(f"Error during worker/thread cleanup: {e}", exc_info=True)


class IODListLoaderServiceMediator(BaseServiceMediator):
    """Acts as a bridge between the service worker and the Qt-based application controller.

    Manages background worker threads, listens to blinker signals from the service layer,
    and emits Qt signals for the UI layer. This class is tightly coupled to the Qt framework and
    acts as a bridge between the UI and the business logic.

    This mediator is specific to the IODListLoaderWorker.
    """

    iodlist_progress_signal = Signal(object, Progress)
    iodlist_loaded_signal = Signal(object, object)
    iodlist_error_signal = Signal(object, str)

    def __init__(self, model: Any, logger: Any, parent: Optional[QObject] = None) -> None:
        """Initialize the service controller with the model and logger.

        Connects blinker signals from the IODListLoaderWorker to Qt signals for the UI.
        """
        super().__init__(model, logger, parent)

    def start_iodlist_worker(self) -> Tuple["IODListLoaderWorker", threading.Thread]:
        """Start the IOD list loader worker in a background thread.

        Returns:
            tuple: The worker and the thread objects.

        """
        # Create a thread-safe queue for communication
        self._event_queue = queue.Queue()
        self._worker = IODListLoaderWorker(self.model, logger=self.logger, event_queue=self._event_queue)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._thread.start()

        # Start a QTimer to poll the queue for events
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_event_queue)
        self._poll_timer.start(50)  # Poll every 50ms

        return self._worker, self._thread

    def _on_iodlist_progress(self, sender: object = None, progress: Progress = None) -> None:
        """Translate blinker progress signal (receives a Progress object) to Qt signal."""
        if progress is not None:
            self.iodlist_progress_signal.emit(sender, progress)

    def _on_iodlist_loaded(self, sender: object, iod_modules: object) -> None:
        """Translate blinker loaded signal to Qt signal."""
        self.iodlist_loaded_signal.emit(sender, iod_modules)
        self.cleanup_worker_thread()

    def _on_iodlist_error(self, sender: object, message: str) -> None:
        """Translate blinker error signal to Qt signal."""
        self.iodlist_error_signal.emit(sender, message)
        self.cleanup_worker_thread()

    def _poll_event_queue(self) -> None:
        """Poll the event queue for worker events and emit Qt signals."""
        while not self._event_queue.empty():
            event_type, data = self._event_queue.get()
            if event_type == "progress":
                self.iodlist_progress_signal.emit(self, data)
            elif event_type == "loaded":
                self.iodlist_loaded_signal.emit(self, data)
                self.cleanup_worker_thread()
                self._poll_timer.stop()
            elif event_type == "error":
                self.iodlist_error_signal.emit(self, data)
                self.cleanup_worker_thread()
                self._poll_timer.stop()


class IODModelLoaderServiceMediator(BaseServiceMediator):
    """Mediator for loading a single IOD model in a background thread."""

    iodmodel_progress_signal = Signal(object, Progress)
    iodmodel_loaded_signal = Signal(object, object)
    iodmodel_error_signal = Signal(object, str)

    def __init__(self, model: Any, logger: Any, parent: Optional[QObject] = None) -> None:
        """Initialize the service mediator for loading a single IOD model."""
        super().__init__(model, logger, parent)

    def start_iodmodel_worker(self, table_id: str):
        """Start the IOD model loader worker in a background thread."""
        self._event_queue = queue.Queue()
        self._worker = IODModelLoaderWorker(self.model, table_id, logger=self.logger, event_queue=self._event_queue)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._thread.start()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_event_queue)
        self._poll_timer.start(50)

        return self._worker, self._thread

    def _poll_event_queue(self):
        while not self._event_queue.empty():
            event_type, data = self._event_queue.get()
            if event_type == "progress":
                self.iodmodel_progress_signal.emit(self, data)
            elif event_type == "loaded":
                self.iodmodel_loaded_signal.emit(self, data)
                self.cleanup_worker_thread()
                self._poll_timer.stop()
            elif event_type == "error":
                self.iodmodel_error_signal.emit(self, data)
                self.cleanup_worker_thread()
                self._poll_timer.stop()
