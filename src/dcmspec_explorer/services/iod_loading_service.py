"""IOD Loader Services for DCMspec Explorer."""

import logging
import queue
import threading
from typing import Any

from dcmspec_explorer.services.progress_observer import ServiceProgressObserver


class IODListLoaderWorker:
    """Load IOD list in a background thread."""

    def __init__(self, model: Any, logger: logging.Logger, event_queue: queue.Queue) -> None:
        """Initialize the worker with the model to load IOD list.

        Args:
            model: The model instance to use for loading the IOD list.
            logger: The logger instance for logging progress and errors.
            event_queue: The event queue to put progress updates into.

        """
        self.model = model
        self.logger = logger
        self.event_queue = event_queue

    def run(self) -> None:
        """Run the worker to load IOD list and send events to the event queue."""
        # Log thread information
        self.logger.debug(f"TreeviewLoaderWorker created in thread: {threading.current_thread().name}")

        # Use a ServiceProgressObserver instance for dcmspec to report progress updates into the event queue
        progress_observer = ServiceProgressObserver(self.event_queue)

        try:
            iod_modules = self.model.load_iod_list(progress_observer=progress_observer)
            self.event_queue.put(("loaded", iod_modules))
        except Exception as e:
            self.event_queue.put(("error", str(e)))
