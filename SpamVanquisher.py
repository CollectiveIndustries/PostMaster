import logging
import threading
import time
from lib.Daemon import DaemonThread
from lib.config import config
from lib.post import PostOffice
from lib.logs import LogRotation
from lib.MailNet import MailNet

def process_mail(email_list, src_folder, dest_folder):
    logging.info(f"Moving {len(email_list)} emails from {src_folder} to {dest_folder}")
    for email in email_list:
        email_id = email[0]  # Extract email_id from the tuple
        try:
            POBox.move(src_folder, dest_folder, email_id)
            logging.debug(f"Email {email_id} moved from {src_folder} to {dest_folder}.")
        except Exception as e:
            logging.error(f"Failed to move email {email_id}: {e}")

# Usage Example
if __name__ == "__main__":
    # Folder settings
    spam_folder = config.SPAM_FOLDER
    ham_folder = config.HAM_FOLDER
    infected_folder = config.INFECTED_FOLDER
    spam_learn = config.SPAM_LEARN
    ham_learn = config.HAM_LEARN

    def LogRotate(event: threading.Event):
        Logger.run()

    def Trainer(event: threading.Event, stop_event: threading.Event, scan_interval: int = 300):
        while not stop_event.is_set():        
            logging.info("Training task started.")
            NeuralNet.load_model()
            Spam = POBox.fetch_emails(spam_learn)
            SpamLabels = [1] * len(Spam)
            NeuralNet.train(Spam,labels=SpamLabels)
            logging.info(f"Spam Training completed: {len(Spam)} processed.")
            Ham = POBox.fetch_emails(ham_learn)
            HamLabels = [0] * len(Ham)
            NeuralNet.train(Ham,HamLabels)
            logging.info(f"Ham Training completed: {len(Ham)} processed.")
            NeuralNet.save_model()

            event.set()   # Notify the classification task that training is done
            logging.debug(f"Training event set()")

            logging.info("Moving Trained Emails.")
            process_mail(Spam,spam_learn,spam_folder)
            process_mail(Ham,ham_learn,ham_folder)
            time.sleep(scan_interval)
        logging.info("Stop Called! shutting Trainer thread down!")


    def PostMan(event: threading.Event, stop_event: threading.Event, scan_interval: int = 300):
        while not stop_event.is_set():
            logging.info("Classification task waiting for training.")
            event.wait()  # Wait for the training task to complete
            logging.info("Classification task started after training.")
            
            # Load the trained model
            NeuralNet.load_model()
            logging.info("Model loaded for classification.")

            emails_to_classify = POBox.fetch_emails(config.INBOX)
            mail_txt = []
            mail_ids = []

            for email in emails_to_classify:
                email_id, subject, sender, recipient, payload = email
                # Preprocess email data (e.g., combine fields for input to model)
                mail_txt.append(f"{subject} {sender} {payload}")
                mail_ids.append(email_id)

            predictions = NeuralNet.classify(mail_txt)

            for email_id, classification in zip(mail_ids, predictions):
                logging.info(f"Email ID {email_id} classified as {'Spam' if classification > 0.5 else 'Ham'}.")
                label = 'Spam' if classification > 0.5 else 'Ham'
                if label == "Spam":
                    destination_folder = config.SPAM_FOLDER
                else:
                    destination_folder = config.HAM_FOLDER
                
                # Move the email to the appropriate folder
                POBox.move(config.INBOX, destination_folder, email_id)
        
            logging.info("Classification task completed.")
            time.sleep(scan_interval)
        logging.info("Stop Called! shutting PostMan thread down!")

    StopEvent = threading.Event()
    ScanTime = int(config.SCAN_TIME)

    Logger = LogRotation(StopEvent)
    POBox = PostOffice()
    NeuralNet = MailNet()

    LogDaemon = DaemonThread(name="LogRotation", target=LogRotate)
    TrainingDaemon = DaemonThread(name="Trainer", target=Trainer, args=(StopEvent, config.SCAN_TIME))
    OfficeDaemon = DaemonThread(name="PostMan", target=PostMan, args=(StopEvent, config.SCAN_TIME))

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
