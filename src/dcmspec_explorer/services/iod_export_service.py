"""IOD Export Service for DCMspec Explorer."""

import logging
import queue
import threading
from typing import Any

from dcmspec.iod_spec_printer import IODSpecPrinter


class IODExportWorker:
    """Export a loaded IOD spec model to CSV or Excel in a background thread."""

    def __init__(
        self, iod_model: Any, fmt: str, output_path: str, logger: logging.Logger, event_queue: queue.Queue
    ) -> None:
        """Initialize the worker with the model to export and the target format/path.

        Args:
            iod_model: The loaded SpecModel to export.
            fmt: Export format, "csv" or "xlsx".
            output_path: Destination file path.
            logger: The logger instance for logging progress and errors.
            event_queue: The event queue to put the outcome event into.

        """
        self.iod_model = iod_model
        self.fmt = fmt
        self.output_path = output_path
        self.logger = logger
        self.event_queue = event_queue

    def run(self) -> None:
        """Run the worker to export the IOD model and send the outcome to the event queue."""
        self.logger.debug(f"IODExportWorker created in thread: {threading.current_thread().name}")
        try:
            printer = IODSpecPrinter(self.iod_model, logger=self.logger, output=self.output_path)
            if self.fmt == "csv":
                printer.print_csv()
            elif self.fmt == "xlsx":
                printer.print_xlsx()
            else:
                raise ValueError(f"Unsupported export format: {self.fmt}")
            self.event_queue.put(("loaded", self.output_path))
        except Exception as e:
            self.logger.exception(f"Failed to export IOD model to {self.output_path}")
            self.event_queue.put(("error", str(e)))
