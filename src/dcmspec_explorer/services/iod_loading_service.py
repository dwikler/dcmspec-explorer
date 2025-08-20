"""IOD Loader Services for DCMspec Explorer."""

import threading
from blinker import Signal

from dcmspec_explorer.services.progress_observer import ServiceProgressObserver


class IODListLoaderWorker:
    """Load IOD list in a background thread."""

    finished = Signal("iodlistloader_finished")
    error = Signal("iodlistloader_error")
    progress = Signal("iodlistloader_progress")

    def __init__(self, model, logger):
        """Initialize the worker with the model to load IOD list."""
        self.model = model
        self.logger = logger

    def run(self):
        """Run the worker to load IOD list."""
        # Log thread information
        self.logger.debug(f"TreeviewLoaderWorker created in thread: {threading.current_thread().name}")

        # Create a progress observer that emits a blinker signal with the Progress object
        progress_observer = ServiceProgressObserver(IODListLoaderWorker.progress)

        try:
            iod_modules = self.model.load_iod_list(progress_observer=progress_observer)
            IODListLoaderWorker.finished.send(self, iod_modules=iod_modules)
        except Exception as e:
            IODListLoaderWorker.error.send(self, message=str(e))
