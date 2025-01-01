import logging
import threading
import time
import signal
from lib.Daemon import DaemonThread
from lib.config import config
from lib.yarn import LogRotation, TrainerThread, ClassificationThread

# Register signal handler for SIGTERM
def graceful_shutdown(signum, _frame):
    logging.info(f"Received signal {signum}, shutting down gracefully.")
    StopEvent.set()

# Usage Example
if __name__ == "__main__":
    # General configs
    spam_folder = config.SPAM_FOLDER
    ham_folder = config.HAM_FOLDER
    infected_folder = config.INFECTED_FOLDER
    spam_learn = config.SPAM_LEARN
    ham_learn = config.HAM_LEARN
    mail_que = config.INBOX
    ScanTime = int(config.SCAN_TIME)
    batch_size = config.BATCH_SIZE

    # Additional Resources
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # Threading resources
    model_lock = threading.RLock()
    StopEvent = threading.Event()
    ProcEvent = threading.Barrier(2)

    # Class Objects
    Logger = LogRotation(StopEvent)
    SpamTrain = TrainerThread((spam_learn, spam_folder, 0), batch_size, StopEvent, ProcEvent, model_lock)
    HamTrain = TrainerThread((ham_learn, ham_folder, 1), batch_size , StopEvent,ProcEvent, model_lock)
    Classification = ClassificationThread(mail_que, StopEvent, ProcEvent, batch_size)

    # List of threads (DaemonThread calls directly placed in the list)
    threads = [
        DaemonThread(name="LogRotation", target=Logger.run),
        DaemonThread(name="Trainer-Spam", target=SpamTrain.run),
        DaemonThread(name="Trainer-Ham", target=HamTrain.run),
        DaemonThread(name="PostMan", target=Classification.run),
    ]
        # Start all threads
    try:
        for thread in threads:
            logging.info(f"Starting thread: {thread.name}")
            thread.start()

        logging.info("Service is running.")

        # Main service loop: Wait for the stop signal
        while not StopEvent.is_set():
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down gracefully.")
        StopEvent.set()
    except Exception as e:
        logging.error(f"Unexpected error occurred: {e}", exc_info=True)
        StopEvent.set()
    finally:
        logging.info("Stopping all threads.")

        # Ensure threads stop and join gracefully
        for thread in threads:
            logging.info(f"Waiting for thread to exit: {thread.name}")
            thread.join()
        logging.info("All threads have exited cleanly.")
