import logging
import threading
import time
import os
import signal
from lib.Daemon import DaemonThread
from lib.config import config
from lib.post import PostOffice
from lib.logs import LogRotation
from lib.MailNet import MailNet
from lib.helper import extract_email_data, log_progress

def bulk_move(email_list, src_folder, dest_folder):
    total_mail = len(email_list)
    start_time = time.time()
    email_ids = []
    logging.info(f"Moving {total_mail} emails from {src_folder} to {dest_folder}")
    for index, email in enumerate(email_list, start=1):
        email_ids.append(email[0])  # Extract email_id from the tuple
        
    try:
        POBox.bulk_move(src_folder, dest_folder, email_ids)
    except Exception as e:
        logging.error(f"Failed to move email {email_ids}: {e}")
        
        # Log progress every 100 emails
        if index % 100 == 0 or index == total_mail:
            log_progress(index,total_mail, start_time)
    logging.info(f"Bulk move completed. {total_mail} emails processed from {src_folder} to {dest_folder}.")

# Usage Example
if __name__ == "__main__":
    # Folder settings
    spam_folder = config.SPAM_FOLDER
    ham_folder = config.HAM_FOLDER
    infected_folder = config.INFECTED_FOLDER
    spam_learn = config.SPAM_LEARN
    ham_learn = config.HAM_LEARN

    def LogRotate(stop_event: threading.Event):
        log_file = config.LOG_FILE

        logging.info("Log rotation thread started. Monitoring file: %s", log_file)
        while not stop_event.is_set():
            try:
                if os.path.exists(log_file):
                    file_size = os.path.getsize(log_file)
                    logging.debug("Current log file size: %d bytes", file_size)
                    if file_size >= config.MAX_SIZE:
                        logging.warning("Log file size exceeded threshold: %s", log_file)
                        Logger.rotate()
                else:
                    with open(log_file, 'w') as log_file:
                        log_file.write("")  # Initialize an empty log file
            except Exception as e:
                logging.error("Error in log rotation thread: %s", e, exc_info=True)
            time.sleep(config.CHECK_INTERVAL)
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

                # Define threads to fetch emails in parallel
                def fetch_spam():
                    nonlocal Spam
                    Spam = POBox.fetch_emails(spam_learn)

                def fetch_ham():
                    nonlocal Ham
                    Ham = POBox.fetch_emails(ham_learn)

                Spam, Ham = [], []
                spam_fetch_thread = threading.Thread(target=fetch_spam, name="Trainer-FetchSpam")
                ham_fetch_thread = threading.Thread(target=fetch_ham, name="Trainer-FetchHam")

                spam_fetch_thread.start()
                ham_fetch_thread.start()

                spam_fetch_thread.join()
                ham_fetch_thread.join()

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
                spam_move_thread = threading.Thread(target=bulk_move, args=(Spam, spam_learn, spam_folder), name="SpamBulkMove")
                ham_move_thread = threading.Thread(target=bulk_move, args=(Ham, ham_learn, ham_folder), name="HamBulkMove")

                spam_move_thread.start()
                ham_move_thread.start()

                spam_move_thread.join()
                ham_move_thread.join()
                logging.info("All bulk move operations completed.")

                # Wait before retraining
                logging.info(f"Finished processing training data. Waiting {scan_interval} seconds to retrain.")
                time.sleep(scan_interval)
                sync_event.clear()

            except Exception as e:
                logging.error(f"An error occurred in the training loop: {e}", exc_info=True)

        logging.info("Stop called! Shutting Trainer thread down.")


    def PostMan(sync_event: threading.Event, stop_event: threading.Event, scan_interval: int = None):
        scan_interval = scan_interval or config.SCAN_TIME
        logging.debug(f"sync_event ID: {id(sync_event)}")
        while not stop_event.is_set():
            logging.info("Classification task waiting for training.")
            sync_event.wait()  # Wait for the training task to complete
            logging.info("Classification task started after training.")

            # Load the trained model
            NeuralNet.load_model()
            logging.info(f"Model loaded for classification. fetching new mail from {config.INBOX}")

            emails_to_classify = POBox.fetch_emails(config.INBOX)
            mail_txt = []
            mail_ids = []

            logging.info("Mail fetched running Classification.")
            for email in emails_to_classify:
                email_id, subject, sender, recipient, payload = email
                # Preprocess email data (e.g., combine fields for input to model)
                mail_txt.append(extract_email_data(email)) 
                mail_ids.append(email_id)

            predictions = NeuralNet.classify(mail_txt)
            logging.info(f"{len(emails_to_classify)} emails classified.")
            logging.info(f"Sorting and moving {len(emails_to_classify)} emails.")

            total_emails = len(mail_ids)
            start_time = time.time()

            for index, (email_id, classification) in enumerate(zip(mail_ids, predictions), start=1):
                # Log classification for debugging
                logging.debug(f"Email ID {email_id} classified as {'Spam' if classification > 0.5 else 'Ham'}.")

                label = 'Spam' if classification > 0.5 else 'Ham'
                destination_folder = config.SPAM_FOLDER if label == "Spam" else config.HAM_FOLDER

                # Move the email to the appropriate folder
                POBox.move(config.INBOX, destination_folder, email_id)

                # Log progress every 100 emails
                if index % 100 == 0 or index == total_emails:
                    log_progress(index,total_emails,start_time)
        
            logging.info(f"{len(mail_ids)} emails sorted and moved. Waiting for next scan event")
            time.sleep(scan_interval)
        logging.info("Stop Called! shutting PostMan thread down!")

    StopEvent = threading.Event()
    ProcEvent = threading.Event()

    ScanTime = int(config.SCAN_TIME)

    Logger = LogRotation()
    POBox = PostOffice(StopEvent)
    NeuralNet = MailNet()

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
