import logging
import threading

class DaemonThread(threading.Thread):
    def __init__(self, name: str, target: callable, args: tuple = (), kwargs=None):
        """Initializes the daemon with a given name, target method, args, and interval for periodic tasks."""
        super().__init__(name=name, target=target, args=args, kwargs=kwargs)
        self.name = name
        self.target = target
        self.args = args
        self.kwargs = kwargs if kwargs else {}
        self.thread = None  # Thread instance

        logging.basicConfig(level=logging.INFO)
        logging.info(f"DaemonThread {self.name} initilized.")

    def start(self):
        """Start the daemon thread."""
        if self.is_alive():
            logging.warning(f"Thread '{self.name}' is already running.")
            return
    
        logging.info(f"Starting thread '{self.name}'.")
        super().start()

    def stop(self):
        """Stop the daemon thread."""
        if self.thread and self.thread.is_alive():
            logging.info(f"Stopping thread '{self.name}'.")
            self.thread.join()  # Wait for the thread to finish
            logging.info(f"Thread '{self.name}' has stopped.")
        else:
            logging.warning(f"Thread '{self.name}' is not running.")

    def is_running(self):
        """Check if the thread is running."""
        return self.thread is not None and self.thread.is_alive()

    def is_stopped(self):
        """Check if the stop event has been set."""
        return self.stop_event.is_set()
