"""Progress observer class for DCMspec Explorer Services."""

import queue

from dcmspec.progress import Progress, ProgressObserver


class ServiceProgressObserver(ProgressObserver):
    """Define a progress observer for service/worker threads that puts progress updates into a queue.

    This observer is intended for use in service or worker threads. When it receives a progress
    notification (a `Progress` object), it puts a ('progress', Progress) tuple into the provided queue.
    This allows controllers or other parts of the application to handle progress updates,
    such as updating the UI or logging, in a framework-agnostic and thread-safe way.

    Args:
        event_queue (queue.Queue): A thread-safe queue to put progress events into.

    Example:
        In your service worker class module:

            from dcmspec.progress import ServiceProgressObserver

            class TaskServiceWorker:
                def __init__(self, model, event_queue):
                    self.event_queue = event_queue
                    self.progress_observer = ServiceProgressObserver(self.event_queue)
                    self.model = model

                def run(self):
                    self.model.load_iod_list(progress_observer=self.progress_observer)

        In your mediator/controller:

            def poll_events(self):
                while not self.event_queue.empty():
                    event_type, progress = self.event_queue.get()
                    if event_type == 'progress':
                        print(f"Task Progress: {progress.percent}% (status: {progress.status})")

    """

    def __init__(self, event_queue: queue.Queue) -> None:
        """Initialize the ServiceProgressObserver with a thread-safe event queue.

        Args:
            event_queue (queue.Queue): A thread-safe queue to put progress events into.

        """
        self.event_queue = event_queue

    def __call__(self, progress: Progress) -> None:
        """Handle progress updates by putting them into the event queue.

        Args:
            progress (Progress): The progress update to handle.

        """
        self.event_queue.put(("progress", progress))
