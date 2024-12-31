import logging
import threading
import time
import os
import signal
from lib.Daemon import DaemonThread
from lib.config import config
from lib.post import PostOffice, Email
from lib.logs import LogRotation
from lib.MailNet import MailNet
from lib.database import EmailDatabase
from lib.utils import extract_email_data, log_progress, interruptible_sleep

# Refactor this class to use the PostOffice.Bulk_Move() method instead
# TODO add hash lookup for cross checking mail lables
class MailProcessor:
    def __init__(self, stop_event):
        self.stop_event = stop_event

    def batch_move(self, src_folder, dest_folder):
        """
        Generalized method to move emails from a source folder to a destination folder
        in bulk, based on classification retrieved from the database. 
        Ensures that only emails logged in the DB are moved.
        """
        start_time = time.time()
        BulkOffice = PostOffice(self.stop_event, src_folder)  # Each thread creates its own connection
        BulkOffice.connect()
        db_bulk = EmailDatabase(
            host=config.SQL_HOST,
            user=config.SQL_USER,
            password=config.SQL_PASSWORD,
            database=config.SQL_DATABASE,
            port=config.SQL_PORT
        )

        try:
            for batch in BulkOffice.fetch_batch(config.BATCH_SIZE):
                # Check if the email hash is already in the database
                for email in batch:
                    if db_bulk.is_trained(email.X_GM_MSGID):
                        # Email is logged in the database, so we can proceed with classification
                        classification = db_bulk.get_classification(email.X_GM_MSGID)

                        if classification is not None:
                            classification_id = classification[0]

                            # Determine the destination folder based on the classification ID
                            dest_folder = db_bulk.get_folder_for_classification(classification_id)

                            if dest_folder:
                                # Move the email to the destination folder
                                BulkOffice.move(dest_folder, email.X_GM_MSGID)
                                logging.debug(f"Email {email.X_GM_MSGID} moved to {dest_folder} with classification ID {classification_id}.")
                            else:
                                logging.warning(f"No destination folder found for classification ID {classification_id}. Email {email.X_GM_MSGID} left in {src_folder}.")
                        else:
                            logging.warning(f"Email {email.X_GM_MSGID} could not be classified. Leaving in {src_folder}.")
                    else:
                        logging.warning(f"Email {email.X_GM_MSGID} is not logged in the database. Skipping move.")
        except Exception as e:
            logging.error(f"An error occurred during bulk_move: {e}", exc_info=True)
        finally:
            # Clean up resources
            db_bulk.close()
            end_time = time.time()

            logging.info(f"Bulk move operation completed in {end_time - start_time:.2f} seconds.")

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
        scan_interval = scan_interval or config.SCAN_TIME
        logging.info("Training thread started.")
        logging.debug(f"sync_event ID: {id(sync_event)}")

        model_lock = threading.RLock()  # Lock for model access

        while not stop_event.is_set():
            try:
                with model_lock:
                    NeuralNet.load_model()
                    logging.info("Model loaded for training.")

                def train_mailbox(mailbox_name, classification_number, destination_folder):
                    nonlocal model_lock

                    db_thread = EmailDatabase(
                        host=config.SQL_HOST,
                        user=config.SQL_USER,
                        password=config.SQL_PASSWORD,
                        database=config.SQL_DATABASE,
                        port=config.SQL_PORT
                    )
                    mailProc = MailProcessor(stop_event)

                    try:
                        MailBox = PostOffice(StopEvent, mailbox_name)  # PostOffice is thread-safe and connects in constructor
                        MailBox.connect()
                        db_thread.add_folder_and_classification(classification_number,destination_folder)

                        # Calculate the total number of emails and batches
                        total_emails = MailBox.total_emails(mailbox_name)
                        total_batches = (total_emails // config.BATCH_SIZE) + (1 if total_emails % config.BATCH_SIZE != 0 else 0)

                        logging.info(f"Processing {total_emails} emails in {total_batches} batches from {mailbox_name}.")

                        batch_num = 0
                        for batch in MailBox.fetch_batch(batch_size=config.BATCH_SIZE):  # Fetch batches as a generator
                            batch_emails = []
                            batch_num += 1  # Track the current batch number

                            for email in batch:
                                # Check if the email hash is already in the database
                                if not db_thread.is_trained(email.X_GM_MSGID):
                                    db_thread.add_email_hash(email.hash, email.X_GM_MSGID, classification_number)
                                    batch_emails.append(email)
                                elif db_thread.is_trained(email.X_GM_MSGID):
                                    # Email is already trained but still in the source folder
                                    logging.info(f"Email {email.X_GM_MSGID} is already trained but still in {mailbox_name}. Moving to {destination_folder}.")
                                    MailBox.move(destination_folder, email.X_GM_MSGID)  # Move email to destination folder
                            
                            if batch_emails:
                                with model_lock:
                                    logging.info("Training model.")
                                    labels = [classification_number] * len(batch_emails)
                                    NeuralNet.train(batch_emails, labels=labels)
                                    logging.info(f"Trained on {len(batch_emails)} emails from batch {batch_num} of {total_batches}.")
                                    MailBox.keep_alive()  # Send NOOP to keep the connection alive
                            
                                    NeuralNet.save_model()
                                    logging.info(f"Model saved after batch {batch_num} of {total_batches}.")
                            
                                # Update trained flag for batch
                                for email in batch_emails:  # Only process emails that were newly trained
                                    db_thread.set_trained_flag(email.hash)
                            
                                # Move newly trained emails to the destination folder
                                mailProc.batch_move(mailbox_name, destination_folder)
                                logging.info(f"Moved {len(batch_emails)} emails to {destination_folder}.")
                            else:
                                logging.info(f"No pending emails in {mailbox_name}. Training skipped.")
                            
                            logging.info(f"Fetching batch {batch_num+1} of {total_batches}.")

                    finally:
                        db_thread.close()
                        MailBox.close()
                        MailBox.logout()

                threads = [
                    threading.Thread(target=train_mailbox, args=(spam_learn, 1, spam_folder), name="Trainer-ProcessSpam"),
                    threading.Thread(target=train_mailbox, args=(ham_learn, 0, ham_folder), name="Trainer-ProcessHam")
                ]

                for thread in threads:
                    thread.start()

                for thread in threads:
                    thread.join()

                sync_event.set()
                logging.debug("Thread sync event set.")

            except Exception as e:
                logging.error(f"An error occurred in the Trainer thread: {e}", exc_info=True)

            if scan_interval:
                stop_event.wait(scan_interval)

        logging.info("Trainer thread exiting.")

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

            POBox = PostOffice(StopEvent,config.INBOX)
            POBox.connect()

            logging.info("Mail fetched running Classification.")
            mail_count = 0
            for batch in POBox.fetch_batch(config.BATCH_SIZE):  # fetch_batch is now a generator yielding batches
                for email in batch:  # Each batch is a list of emails
                    try:
                        email.classification = NeuralNet.classify(extract_email_data(email))
                    except Exception as e:
                        logging.error(f"Error classifying email {email.uid}: {e}", exc_info=True)
                        email.classification = None  # Mark as unclassified
                    mail_count += 1  # Increment mail count for each email processed

            logging.info(f"Total emails classified: {mail_count}")
            logging.info(f"Sorting and moving {len(mail_count)} emails.")

            start_time = time.time()

            for index, mail in enumerate(mail_count, start=1):
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
                if index % 100 == 0 or index == mail_count:
                    log_progress(index,mail_count,start_time)

            logging.info(f"{len(mail_count)} emails sorted and moved. Waiting for next scan event")
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
