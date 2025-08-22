import logging
import signal
import threading
import time

from lib.config import config
from lib.yarn import ClassificationThread, LogRotation, TrainerThread


# Register signal handler for SIGTERM
def graceful_shutdown(signum, _frame):
    logging.info(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
        f"Received signal {signum}, shutting down gracefully."
    )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
    StopEvent.set()  # pylint: ignore=possibly-used-before-assignment  # FIXME pylint: E0011: Unrecognized file option 'ignore' (unrecognized-inline-option)  # FIXME pylint: E0606: Possibly using variable 'StopEvent' before assignment (possibly-used-before-assignment)


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

    # Additional Resources
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # Threading resources
    model_lock = threading.RLock()
    StopEvent = threading.Event()
    ProcEvent = threading.Barrier(3)

    # Class Objects
    Logger = LogRotation(StopEvent)
    SpamTrain = TrainerThread(
        name="Trainer-Spam",
        mailbox=(spam_learn, spam_folder, 0),
        stop_event=StopEvent,
        barrier=ProcEvent,
        model_lock=model_lock,
        batch_size=config.BATCH_SIZE,
    )
    HamTrain = TrainerThread(
        name="Trainer-Ham",
        mailbox=(ham_learn, ham_folder, 1),
        stop_event=StopEvent,
        barrier=ProcEvent,
        model_lock=model_lock,
        batch_size=config.BATCH_SIZE,
    )
    Classification = ClassificationThread(
        name="PostMan", mailbox=mail_que, stop_event=StopEvent, barrier=ProcEvent, batch_size=config.BATCH_SIZE
    )

    # List of threads (DaemonThread calls directly placed in the list)
    threads = [Logger, SpamTrain, HamTrain, Classification]
    # Start all threads
    try:
        for thread in threads:
            logging.info(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                f"Starting thread: {thread.name}"
            )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
            thread.start()

        logging.info("Service is running.")

        # Main service loop: Wait for the stop signal
        while not StopEvent.is_set():
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down gracefully.")
        StopEvent.set()
    except Exception as e:
        logging.error(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
            f"Unexpected error occurred: {e}", exc_info=True
        )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
        StopEvent.set()
    finally:
        logging.info("Stopping all threads.")

        # Ensure threads stop and join gracefully
        for thread in threads:
            logging.info(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                f"Waiting for thread to exit: {thread.name}"
            )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
            thread.stop()
            thread.join()
        logging.info("All threads have exited cleanly.")
