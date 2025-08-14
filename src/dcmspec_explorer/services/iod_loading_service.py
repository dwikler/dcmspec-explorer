"""IOD Loader Services for DCMspec Explorer."""

import threading
from PySide6.QtCore import QObject, Signal


class IODListLoaderWorker(QObject):
    """Load IOD list in a background thread."""

    finished = Signal(list)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, model, logger):
        """Initialize the worker with the model to load IOD list."""
        super().__init__()
        self.model = model
        self.logger = logger

    def run(self):
        """Run the worker to load IOD list."""
        # Log thread information
        self.logger.debug(f"TreeviewLoaderWorker created in thread: {threading.current_thread().name}")

        try:
            iod_modules = self.model.load_iod_list(progress_callback=self.progress.emit)
            self.finished.emit(iod_modules)
        except Exception as e:
            self.error.emit(str(e))
