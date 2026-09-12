"""Explanatory Section Loader Service for DCMspec Explorer."""

import logging
import queue
import threading
from typing import Any


class SectionLoaderWorker:
    """Load a single explanatory section in a background thread."""

    def __init__(self, model: Any, section_id: str, logger: logging.Logger, event_queue: queue.Queue) -> None:
        """Initialize the worker with the model and section id.

        Args:
            model: The model instance to use for loading the section.
            section_id: The id of the section to load.
            logger: The logger instance for logging progress and errors.
            event_queue: The event queue to put progress updates into.

        """
        self.model = model
        self.section_id = section_id
        self.logger = logger
        self.event_queue = event_queue

    def run(self) -> None:
        """Run the worker to load a single explanatory section and send events to the event queue."""
        self.logger.debug(f"SectionLoaderWorker created in thread: {threading.current_thread().name}")
        try:
            section_model = self.model.get_or_load_section(self.section_id, self.logger)
            self.event_queue.put(("loaded", section_model))
        except Exception as e:
            self.logger.exception(f"Failed to load explanatory section for section_id: {self.section_id}")
            self.event_queue.put(("error", str(e)))
