"""Progress observer class for DCMspec Explorer Services."""

from blinker import Signal
from dcmspec.progress import Progress, ProgressObserver


class ServiceProgressObserver(ProgressObserver):
    """Define a progress observer for service/worker threads that emits a blinker Signal with each progress update.

    This observer is intended for use in service or worker threads. When it receives a progress
    notification (a `Progress` object), it emits the provided blinker `Signal` with the full
    Progress object. This allows controllers or other parts of the application to handle progress updates,
    such as updating the UI or logging, in a framework-agnostic way.

    Args:
        signal (Signal): A blinker Signal object that will be emitted with the Progress object.

    Example:
        In your service worker class module:

            from blinker import Signal
            from dcmspec.progress import ServiceProgressObserver

            class TaskServiceWorker:
                def __init__(self, model):
                    # Create a blinker Signal for this task's progress updates.
                    self.task_progress = Signal()
                    # Create a ServiceProgressObserver to receive progress updates and emit them via the signal.
                    self.progress_observer = ServiceProgressObserver(self.task_progress)
                    # Store the model reference for use in the run method.
                    self.model = model

                def run(self):
                    # Call the model's method passing the progress observer
                    self.model.load_iod_list(progress_observer=self.progress_observer)

        In your controller:

            # Define a handler for task progress updates
            def on_task_progress(sender, progress):
                print(f"Task Progress: {progress.percent}% (status: {progress.status})")

            # Create the service thread
            service = TaskService(model)
            # Connect the signal to the handler
            service.task_progress.connect(on_task_progress)
            # Start the service thread
            service.run()

    """

    def __init__(self, signal: Signal):
        """Initialize the ServiceProgressObserver with a blinker Signal."""
        self.signal: Signal = signal

    def __call__(self, progress: Progress) -> None:
        """Handle progress updates by emitting the blinker Signal."""
        self.signal.send(self, progress=progress)
