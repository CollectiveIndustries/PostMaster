import logging
import threading
import time
import os
import signal
from lib.Daemon import DaemonThread
from lib.config import config
from lib.post import PostOffice, Email, EmailHasher
from lib.logs import LogRotation
from lib.MailNet import MailNet
from lib.utils import extract_email_data, log_progress, interruptible_sleep

# Refactor this class to use the PostOffice.Bulk_Move() method instead
# TODO add hash lookup for cross checking mail lables
def bulk_move(email_list: list[Email], src_folder, dest_folder):
    total_mail = len(email_list)
    start_time = time.time()
    email_ids = []
    # Connect
    # Fetch Sequence Numbers
    logging.info(f"Moving {total_mail} emails from {src_folder} to {dest_folder}")
    for index, email in enumerate(email_list, start=1):
        email_ids.append(email.uid)  # Extract email_id from the Email Object
        if index % 100 == 0 or index == total_mail:
            log_progress(index, total_mail, start_time)
    try:
        POBox.bulk_move(src_folder, dest_folder, email_ids)
    except Exception as e:
        logging.error(f"Failed to move batch {email_ids}: {e}")

        # Close/Logout

    logging.info(f"Bulk move completed. {total_mail} emails processed from {src_folder} to {dest_folder}.")

# Usage Example
if __name__ == "__main__":
    # General configs
    spam_folder = config.SPAM_FOLDER
    ham_folder = config.HAM_FOLDER
    infected_folder = config.INFECTED_FOLDER
    spam_learn = config.SPAM_LEARN
    ham_learn = config.HAM_LEARN
    ScanTime = int(config.SCAN_TIME)

    # Additional Resources

    # Threading resources
    model_lock = threading.RLock()
    StopEvent = threading.Event()
    ProcEvent = threading.Event()

    # Class Objects
    Logger = LogRotation()
    NeuralNet = MailNet()

    # Thread defs
    def LogRotate(stop_event: threading.Event):
        log_file = config.LOG_FILE

        logging.info("Log rotation thread started. Monitoring file: %s", log_file)
        while not stop_event.is_set():
            try:
                if os.path.exists(log_file):
                    file_size = os.path.getsize(log_file)
                    logging.debug(f"Current log file size: {file_size} bytes. MAX_SIZE: {config.MAX_SIZE}")
                    if file_size >= config.MAX_SIZE:
                        logging.warning(f"Log file size exceeded threshold: {log_file}")
                        Logger.rotate()
                else:
                    with open(log_file, 'w') as log_file:
                        log_file.write("")  # Initialize an empty log file
            except Exception as e:
                logging.error("Error in log rotation thread: %s", e, exc_info=True)
            interruptible_sleep(config.CHECK_INTERVAL, stop_event)
        logging.info("Log rotation thread stopped.")

    def Trainer(sync_event: threading.Event, stop_event: threading.Event, scan_interval: int = None):
        """Trainer thread that fetches emails, trains the neural network, and moves processed data."""
        scan_interval = scan_interval or config.SCAN_TIME
        logging.info("Training thread started.")
        logging.debug(f"sync_event ID: {id(sync_event)}")

        while not stop_event.is_set():
            try:
                NeuralNet.load_model()
                logging.info("Model loaded for training.")
                Spam, Ham = [], []
                HashLock = threading.RLock()

                # Define threads to fetch emails in parallel
                def fetch_mail(mailbox_name, classification_number, result_container):
                    """
                    Generic function to fetch emails and update the hash table.

                    Parameters:
                    - mailbox_name: The mailbox to fetch emails from.
                    - classification_number: Classification number for the emails (e.g., 1 for spam, 0 for ham).
                    - result_container: A nonlocal variable to store the fetched emails.
                    """
                    nonlocal HashLock
                    HashTable = EmailHasher(lock=HashLock)
                    MailBox = PostOffice(StopEvent)
                    MailBox.connect()
                    emails = MailBox.fetch_emails(mailbox_name)
                    MailBox.logout()
                    for e in emails:
                        HashTable.add_email(email_hash=e.hash, classification_number=classification_number)
                    HashTable.save_hash_table()
                    result_container.extend(emails)  # Store fetched emails in the provided container

                # Spawn threads dynamically
                threads = [
                    threading.Thread(target=fetch_mail, args=(spam_learn, 1, Spam), name="Trainer-FetchSpam"),
                    threading.Thread(target=fetch_mail, args=(ham_learn, 0, Ham), name="Trainer-FetchHam")
                ]

                for thread in threads:
                    thread.start()
                
                for thread in threads:
                    thread.join()

                logging.info(f"Fetched {len(Spam)} spam emails and {len(Ham)} ham emails.")

                # Prepare labels
                SpamLabels = [1] * len(Spam)
                HamLabels = [0] * len(Ham)

                # Train the neural network
                logging.info("Starting neural network training.")
                NeuralNet.train(Spam, labels=SpamLabels)
                logging.info(f"Spam training completed: {len(Spam)} processed.")

                NeuralNet.train(Ham, labels=HamLabels)
                logging.info(f"Ham training completed: {len(Ham)} processed.")

                # Save the trained model
                NeuralNet.save_model()
                logging.info("Model saved successfully.")

                # Notify classification task that training is complete
                sync_event.set()
                logging.debug("Thread sync event set.")

                # Move processed training data in parallel
                logging.info("Starting bulk move operations for training data.")
                spam_move_thread = threading.Thread(target=bulk_move, args=(Spam, spam_learn, spam_folder), name="Trainer-SpamBulkMove")
                ham_move_thread = threading.Thread(target=bulk_move, args=(Ham, ham_learn, ham_folder), name="Trainer-HamBulkMove")

                spam_move_thread.start()
                ham_move_thread.start()

                spam_move_thread.join()
                ham_move_thread.join()
                logging.info("All bulk move operations completed.")

                # Wait before retraining
                logging.info(f"Finished processing training data. Waiting {scan_interval} seconds to retrain.")
                interruptible_sleep(scan_interval,stop_event)
                sync_event.clear()

            except Exception as e:
                logging.error(f"An error occurred in the training loop: {e}", exc_info=True)

        logging.info("Stop called! Shutting Trainer thread down.")

    def PostMan(sync_event: threading.Event, stop_event: threading.Event, scan_interval: int = None):
        scan_interval = scan_interval or config.SCAN_TIME
        logging.debug(f"sync_event ID: {id(sync_event)}")
        while not stop_event.is_set():
            if not sync_event.is_set():
                logging.info("Classification task waiting for training.")
                sync_event.wait()  # Wait for the training task to complete
                logging.info("Classification task started after training.")

            # Load the trained model
            NeuralNet.load_model()
            logging.info(f"Model loaded for classification. fetching new mail from {config.INBOX}")

            POBox = PostOffice(StopEvent)
            POBox.connect()
            email_que = POBox.fetch_emails(config.INBOX)

            logging.info("Mail fetched running Classification.")
            for email in email_que:
                try:
                    email.classification = NeuralNet.classify(extract_email_data(email))
                except Exception as e:
                    logging.error(f"Error classifying email {email.uid}: {e}", exc_info=True)
                    email.classification = None  # Mark as unclassified

            logging.info(f"{len(email_que)} emails classified.")
            logging.info(f"Sorting and moving {len(email_que)} emails.")

            total_emails = len(email_que)
            start_time = time.time()

            for index, mail in enumerate(email_que, start=1):
                # Log classification for debugging
                logging.debug(f"Email ID {mail.uid} classified as {'Spam' if mail.classification > 0.5 else 'Ham'}.")

                if mail.classification is not None:
                    label = 'Spam' if mail.classification > 0.5 else 'Ham'
                    destination_folder = config.SPAM_FOLDER if label == "Spam" else config.HAM_FOLDER

                    # Move the email to the appropriate folder
                    POBox.move(config.INBOX, destination_folder, mail.uid)
                else:
                    logging.warning(f"Email ID {mail.uid} could not be classified.")

                # Log progress every 100 emails
                if index % 100 == 0 or index == total_emails:
                    log_progress(index,total_emails,start_time)

            logging.info(f"{len(email_que)} emails sorted and moved. Waiting for next scan event")
            interruptible_sleep(scan_interval,stop_event)
        logging.info("Stop Called! Shutting PostMan thread down!")

    # 
    LogDaemon = DaemonThread(name="LogRotation", target=LogRotate, args=(StopEvent,),)
    TrainingDaemon = DaemonThread(name="Trainer", target=Trainer, args=(ProcEvent, StopEvent),)
    OfficeDaemon = DaemonThread(name="PostMan", target=PostMan, args=(ProcEvent, StopEvent),)

    # Start all threads
    LogDaemon.start()
    TrainingDaemon.start()
    OfficeDaemon.start()

    def graceful_shutdown(signum, _frame):
        logging.info(f"Received signal {signum}, shutting down gracefully.")
        StopEvent.set()

    # Register signal handler for SIGTERM
    signal.signal(signal.SIGTERM, graceful_shutdown)

    try:
        logging.info("Service is running.")
        while not StopEvent.is_set():
            time.sleep(1)  # The main work loop, running until StopEvent is set
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down gracefully.")
        StopEvent.set()

    logging.info("Service stopped.")
