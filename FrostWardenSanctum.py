import logging
import signal
import threading
import time

from lib.config import config
from lib.yarn import ClassificationThread, LogRotation, TrainerThread

# Version and package metadata
__version__ = "0.1.0"

# Register signal handler for SIGTERM
def graceful_shutdown(signum, _frame):
    logging.info(f"Received signal {signum}, shutting down gracefully.")
    StopEvent.set()


# Usage Example
if __name__ == "__main__":
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description='FrostWardenSanctum Email Filtering Service')
    parser.add_argument('--config', help='Path to custom config file')
    parser.add_argument('--log-level', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default='INFO',
                        help='Set the logging level')
    args = parser.parse_args()

    # Initialize logging with specified level
    logging.basicConfig(
        level=args.log_level,
        format=f'%(asctime)s FrostWardenSanctum/{__version__} %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.info(f"Initializing FrostWardenSanctum v{__version__} with log level {args.log_level}")

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
            thread.stop()
            thread.join()
        logging.info("All threads have exited cleanly.")
