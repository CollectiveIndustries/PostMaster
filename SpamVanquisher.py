import logging
import threading
import time
import os
from lib.Daemon import DaemonThread
from lib.config import config
from lib.post import PostOffice
from lib.logs import LogRotation
from lib.MailNet import MailNet

def bulk_move(email_list, src_folder, dest_folder):
    total_mail = len(email_list)
    logging.info(f"Moving {total_mail} emails from {src_folder} to {dest_folder}")
    for index, email in enumerate(email_list, start=1):
        email_id = email[0]  # Extract email_id from the tuple
        try:
            POBox.move(src_folder, dest_folder, str(email_id))
            logging.debug(f"Email {email_id} moved from {src_folder} to {dest_folder}.")
        except Exception as e:
            logging.error(f"Failed to move email {email_id}: {e}")
        
                # Log progress every 100 emails
        if index % 100 == 0:
            logging.info(f"Progress: {index}/{total_mail} emails moved.")
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
        logging.info("Log rotation thread started. Monitoring file: %s", log_file)
        while not stop_event.is_set():
            try:
                if os.path.exists(log_file):
                    file_size = os.path.getsize(log_file)
                    logging.debug("Current log file size: %d bytes", file_size)
                    if file_size >= config.MAX_SIZE_MB:
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
        scan_interval = scan_interval or config.SCAN_TIME
        logging.info("Training thread started.")
        logging.debug(f"sync_event ID: {id(sync_event)}")
        while not stop_event.is_set():        
            NeuralNet.load_model()

            Spam = POBox.fetch_emails(spam_learn)
            SpamLabels = [1] * len(Spam)
            logging.info("Starting NeuralNetwork training")
            NeuralNet.train(Spam,labels=SpamLabels)
            logging.info(f"Spam Training completed: {len(Spam)} processed.")
            
            Ham = POBox.fetch_emails(ham_learn)
            HamLabels = [0] * len(Ham)
            NeuralNet.train(Ham,HamLabels)

            logging.info(f"Ham Training completed: {len(Ham)} processed. saving model")
            NeuralNet.save_model()
            logging.info("Model saved.")

            sync_event.set()   # Notify the classification task that training is done
            logging.debug(f"Thread Sync event set")

            logging.info("Moving Trained Emails.")
            #bulk_move(Spam,spam_learn,spam_folder)
            #bulk_move(Ham,ham_learn,ham_folder)

            # Define threads for spam_learn and ham_learn
            spam_thread = threading.Thread(target=bulk_move, args=(Spam,spam_learn,spam_folder), name="SpamBulkMove")
            ham_thread = threading.Thread(target=bulk_move, args=(Ham,ham_learn,ham_folder), name="HamBulkMove")

            # Start the threads
            spam_thread.start()
            ham_thread.start()

            # Wait for both threads to finish
            spam_thread.join()
            ham_thread.join()

            logging.info("All bulk move operations completed.")

            logging.info(f"Finished moving training data. wating {scan_interval} seconds to retrain.")
            time.sleep(scan_interval)
            sync_event.clear()

        logging.info("Stop Called! shutting Trainer thread down!")


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
                mail_txt.append(f"{subject} {sender} {payload}")
                mail_ids.append(email_id)

            predictions = NeuralNet.classify(mail_txt)
            logging.info(f"{len(emails_to_classify)} emails classified.")

            for email_id, classification in zip(mail_ids, predictions):
                logging.debug(f"Email ID {email_id} classified as {'Spam' if classification > 0.5 else 'Ham'}.")
                label = 'Spam' if classification > 0.5 else 'Ham'
                if label == "Spam":
                    destination_folder = config.SPAM_FOLDER
                else:
                    destination_folder = config.HAM_FOLDER
                
                # Move the email to the appropriate folder
                POBox.move(config.INBOX, destination_folder, email_id)
        
            logging.info(f"{len(mail_ids)} emails sorted and moved. Waiting for next scan event")
            time.sleep(scan_interval)
        logging.info("Stop Called! shutting PostMan thread down!")

    StopEvent = threading.Event()
    ProcEvent = threading.Event()

    ScanTime = int(config.SCAN_TIME)

    Logger = LogRotation()
    POBox = PostOffice(StopEvent)
    NeuralNet = MailNet()

    LogDaemon = DaemonThread(name="LogRotation", target=LogRotate, args=(StopEvent),)
    TrainingDaemon = DaemonThread(name="Trainer", target=Trainer, args=(ProcEvent, StopEvent),)
    OfficeDaemon = DaemonThread(name="PostMan", target=PostMan, args=(ProcEvent, StopEvent),)

    # Start all threads
    LogDaemon.start()
    TrainingDaemon.start()
    OfficeDaemon.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Recieved KeyboardInterrupt")
        StopEvent.set()

    logging.info("MainThread shutting down!")
