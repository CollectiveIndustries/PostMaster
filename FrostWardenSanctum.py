import argparse
import logging
import signal
import sys
import threading
import time

# Ensure MariaDB is running and provisioned before importing config
from lib.db_setup import ensure_database_ready


def parse_early_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
    )
    return parser.parse_known_args()[0]


if __name__ == "__main__":
    early_args = parse_early_args()

    logging.basicConfig(
        level=getattr(logging, early_args.log_level),
        format="%(levelname)s:%(message)s",
    )

    if not ensure_database_ready(config_path=early_args.config):
        sys.exit("Failed to initialize MariaDB. Please check your database setup.")

    from lib.config import config
    from lib.yarn import ClassificationThread, LogRotation, TrainerThread

    # Version and package metadata
    __version__ = "0.1.0"

    # Register signal handler for SIGTERM
    def graceful_shutdown(signum, _frame):
        logging.info("Received signal %s, shutting down gracefully.", signum)
        StopEvent.set()

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
            logging.info("Starting thread: %s", thread.name)
            thread.start()

        logging.info("Service is running.")

        # Main service loop: Wait for the stop signal
        while not StopEvent.is_set():
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down gracefully.")
        StopEvent.set()
    except Exception as e:
        logging.error("Unexpected error occurred: %s", e, exc_info=True)
        StopEvent.set()
    finally:
        logging.info("Stopping all threads.")

        # Ensure threads stop and join gracefully
        for thread in threads:
            logging.info("Waiting for thread to exit: %s", thread.name)
            thread.stop()
            thread.join()
        logging.info("All threads have exited cleanly.")
