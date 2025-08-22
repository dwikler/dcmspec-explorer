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

        def emit_percent(percent):
            """Define callback function to receive progress updates.

            This function emits a custom signal with the progress percentage.
            A nested function is used here because dcmspec checks for types.FunctionType
            to provide backward-compatibility for callbacks expecting an int.
            This check allows plain functions, nested functions, and lambdas, but excludes
            bound methods (like self.emit_percent).
            By using a nested function, we can access 'self' via closure while still
            complying with dcmspec's callback requirements.
            """
            self.progress.emit(percent)

        try:
            iod_modules = self.model.load_iod_list(progress_callback=emit_percent)
            self.finished.emit(iod_modules)
        except Exception as e:
            self.error.emit(str(e))
