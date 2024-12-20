import logging
import threading

class DaemonThread:
    def __init__(self, name: str, target: callable, args: tuple = ()):
        """Initializes the daemon with a given name, target method, args, and interval for periodic tasks."""
        self.name = name
        self.target = target  # The method to run for this thread
        self.args = args      # Arguments to pass to the target method
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
        logging.basicConfig(level=logging.INFO)
        logging.info(f"DaemonThread {self.name} initilized.")

    def start(self):
        """Start the daemon thread."""
        if self.thread and self.thread.is_alive():
            logging.warning(f"Thread '{self.name}' is already running.")
            return

        logging.info(f"Starting thread '{self.name}'.")
        self.stop_event.clear()  # Reset the stop event
        self.thread = threading.Thread(target=self.target, args=(self.stop_event, *self.args), name=self.name)
        self.thread.start()

    def stop(self):
        """Stop the daemon thread."""
        if self.thread and self.thread.is_alive():
            logging.info(f"Stopping thread '{self.name}'.")
            self.stop_event.set()  # Notify the target method to stop
            self.thread.join()  # Wait for the thread to terminate
            self.thread = None  # Reset thread instance
        else:
            logging.warning(f"Thread '{self.name}' is not running.")