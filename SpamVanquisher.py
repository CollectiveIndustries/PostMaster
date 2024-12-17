import logging
from email.header import decode_header
import joblib
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from typing import Tuple, List
import configparser
import email
import imaplib
import logging
import socket
import sys
import threading
import time
import os

CONFIG = configparser.ConfigParser()
CONFIG.read("config.ini")

# Connection settings
EMAIL_ADDRESS = CONFIG.get('ConnectionSettings', 'email_address')
PASSWORD = CONFIG.get('ConnectionSettings', 'password')
IMAP_URL = CONFIG.get('ConnectionSettings', 'url')
IMAP_PORT = int(CONFIG.get('ConnectionSettings', 'port'))

# Folder settings
INBOX = CONFIG.get('Folders', 'inbox')
SPAM_FOLDER = CONFIG.get('Folders', 'spam_folder')
HAM_FOLDER = CONFIG.get('Folders', 'ham_folder')
INFECTED_FOLDER = CONFIG.get('Folders', 'infected_folder')
SPAM_LEARN = CONFIG.get('Folders', 'spam_learn')
HAM_LEARN = CONFIG.get('Folders', 'ham_learn')

# Daemon Settings
TRAINING_DATA_PATH = CONFIG.get('DaemonSettings', 'data_path')
SCAN_TIME = int(CONFIG.get('DaemonSettings', 'scan_time'))

# Log Settings
LOG_FILE = CONFIG.get('Logs', 'log_file')
LOG_LEVEL = CONFIG.get('Logs', 'log_level', fallback="INFO").upper()
MAX_SIZE_MB = int(CONFIG.get('Logs', 'max_size_mb', fallback=10))
BACKUP_COUNT = int(CONFIG.get('Logs', 'backup_count', fallback=5))
CHECK_INTERVAL = int(CONFIG.get('Logs', 'check_interval', fallback=60))

# Clear any existing handlers and setup logging explicitly
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
formatter = logging.Formatter('%(asctime)s %(threadName)s %(name)s[%(process)d]: %(levelname)s: %(message)s')
file_handler.setFormatter(formatter)

logging.root.addHandler(file_handler)
logging.root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

logging.info("Configuration settings loaded.")

def decode_email_header(header_value):
    if not header_value:
        return "(Unknown)"

    decoded_parts = decode_header(header_value)
    header = ""

    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            # Handle the 'unknown-8bit' encoding case
            if encoding == 'unknown-8bit':
                encoding = 'utf-8'  # Fall back to 'utf-8' for 'unknown-8bit'

            # Default to 'utf-8' if encoding is None
            encoding = encoding or 'utf-8'

            try:
                header += part.decode(encoding, errors='ignore')
            except (LookupError, UnicodeDecodeError) as e:
                logging.error(f"Error decoding part with encoding {encoding}: {e}")
                header += part.decode('utf-8', errors='ignore')  # Fallback to utf-8
        else:
            header += part
    return header

class LogRotationThread(threading.Thread):
    def __init__(self):
        """
        Thread to monitor and rotate log files when they exceed a given size.
        """
        super().__init__(name="LogRotationThread")
        self.daemon = True
        self.log_file = LOG_FILE
        self.max_size_mb = MAX_SIZE_MB * 1024 * 1024  # Convert to bytes
        self.backup_count = BACKUP_COUNT
        self.check_interval = CHECK_INTERVAL
        self.stop_event = threading.Event()
        logging.info("Log rotation thread intilized.")

    def start(self):
        logging.info("Starting LogRotationThread...")
        super().start()

    def run(self):
        """Thread run method to monitor the log file size and rotate when needed."""
        logging.info("Log rotation thread started. Monitoring file: %s", self.log_file)
        while not self.stop_event.is_set():
            try:
                if os.path.exists(self.log_file):
                    file_size = os.path.getsize(self.log_file)
                    logging.debug("Current log file size: %d bytes", file_size)
                    if file_size >= self.max_size_mb:
                        logging.warning("Log file size exceeded threshold: %s", self.log_file)
                        self._rotate_logs()
            except Exception as e:
                logging.error("Error in log rotation thread: %s", e, exc_info=True)
            time.sleep(self.check_interval)
        logging.info("Log rotation thread stopped.")

    def stop(self):
        """Stops the log rotation thread."""
        logging.info("Stopping log rotation thread...")
        self.stop_event.set()

    def _rotate_logs(self):
        """Handles rotating the log files by renaming and managing backups."""
        logging.info("Rotating logs for file: %s", self.log_file)
        try:
            # Remove the oldest backup file if it exists
            oldest_log = f"{self.log_file}.{self.backup_count}"
            if os.path.exists(oldest_log):
                os.remove(oldest_log)
                logging.info("Removed oldest log file: %s", oldest_log)

            # Shift the backup files
            for i in range(self.backup_count - 1, 0, -1):
                src = f"{self.log_file}.{i}"
                dst = f"{self.log_file}.{i + 1}"
                if os.path.exists(src):
                    os.rename(src, dst)
                    logging.debug("Renamed log file: %s -> %s", src, dst)

            # Rename the current log file to .1
            rotated_log = f"{self.log_file}.1"
            os.rename(self.log_file, rotated_log)
            logging.info("Rotated current log file to: %s", rotated_log)

            # Recreate the log file
            try:
                with open(self.log_file, 'w') as log:
                    log.write("")
                logging.info("Created new log file: %s", self.log_file)
            except Exception as recreate_error:
                logging.critical("Failed to recreate log file: %s", recreate_error, exc_info=True)

        except Exception as e:
            logging.error("Failed to rotate logs: %s", e, exc_info=True)
            logging.critical("Critical failure during log rotation.")

class PostOffice:
    def __init__(self):
        self.classifier = None
        self.vectorizer = None

        self.model_file = f"{TRAINING_DATA_PATH}/naive_bayes_classifier.pkl"
        self.vectorizer_file = f"{TRAINING_DATA_PATH}/vectorizer.pkl"

        # Thread-safe model access
        self.model_lock = threading.Lock()
        self.model_updated = threading.Event()
        self.running = False
        self.load_model()
        logging.info("PostOffice initilization complete.")

    def load_model(self):
        """Loads the model and vectorizer from disk."""
        try:
            with self.model_lock:
                self.classifier = joblib.load(self.model_file)
                self.vectorizer = joblib.load(self.vectorizer_file)
            logging.info("Model and vectorizer loaded successfully.")
        except FileNotFoundError:
            logging.error("Model or vectorizer file not found. Retraining the model.")
            self.retrain_model()

    def retrain_model(self):
        """Retrains the model with new data, saves it, and moves training emails."""
        logging.info("Retraining the classifier model using training data.")

        # Step 1: Fetch training data and train the model
        emails, labels = self._fetch_training_data()
        vectorizer = CountVectorizer()
        X = vectorizer.fit_transform([e[5] for e in emails])  # Payloads for training
        classifier = MultinomialNB()
        classifier.fit(X, labels)

        with self.model_lock:
            joblib.dump(classifier, self.model_file)
            joblib.dump(vectorizer, self.vectorizer_file)
            self.classifier = classifier
            self.vectorizer = vectorizer
            logging.info("Model and vectorizer updated and saved successfully.")

        # Step 2: Move emails after training
        logging.info("Moving learned emails to their respective final folders.")
        for email in emails:
            email_id = email[0]
            email_type = email[1]

            try:
                if email_type == "ham":
                    self.move(HAM_LEARN, HAM_FOLDER, email_id)
                    logging.info(f"Moved '{email_id}' from '{HAM_LEARN}' to '{HAM_FOLDER}'.")
                elif email_type == "spam":
                    self.move(SPAM_LEARN, SPAM_FOLDER, email_id)
                    logging.info(f"Moved '{email_id}' from '{SPAM_LEARN}' to '{SPAM_FOLDER}'.")
            except Exception as e:
                logging.error(f"Failed to move '{email_id}': {e}")

        # Notify postman thread that model is updated
        logging.info("Notifying threads that the model has been updated.")
        self.model_updated.set()

    def connect(self, mailbox: str, max_retries: int = 5, retry_interval: int = 30):
        """Connects to the IMAP server and selects the mailbox."""
        logging.info(f"Attempting to connect to the IMAP server and access mailbox '{mailbox}'.")
        mail = None
        attempts = 0
        while attempts < max_retries:
            try:
                mail = imaplib.IMAP4_SSL(IMAP_URL, IMAP_PORT)
                mail.login(EMAIL_ADDRESS, PASSWORD)
                mail.select(mailbox)
                logging.info(f"Successfully connected to mailbox '{mailbox}'.")
                return mail
            except (socket.gaierror, imaplib.IMAP4.error) as e:
                logging.error(f"IMAP connection error (attempt {attempts + 1}): {e}")
                time.sleep(retry_interval)
                attempts += 1
        logging.error("Max retries reached. Exiting...")
        sys.exit(1)

    def fetch_emails(self, mailbox: str, email_type: str) -> list:
        """Fetches emails from the specified mailbox."""
        mail = self.connect(mailbox)
        result, data = mail.search(None, "ALL")
        email_ids = data[0].split()
        emails = []

        logging.info(f"Fetching ({len(email_ids)}) emails from mailbox '{mailbox}' for '{email_type}' classification.")
        for email_id in email_ids:
            result, msg_data = mail.fetch(email_id, "(RFC822)")
            if result == "OK":
                msg = email.message_from_bytes(msg_data[0][1])
                subject = decode_email_header(msg.get("Subject", ""))
                sender = decode_email_header(msg.get("From", ""))
                recipient = decode_email_header(msg.get("To", ""))
                payload = self._extract_payload(msg)

                emails.append((email_id.decode(), email_type, subject, sender, recipient, payload))
        logging.info(f"Fetched {len(emails)} emails from mailbox '{mailbox}'.")
        mail.close()
        mail.logout()
        return emails

    def _fetch_training_data(self) -> Tuple[list, list]:
        """Fetches training data from spam/ham learn folders."""
        logging.info("Fetching training data from spam and ham learning folders.")
        spam_emails = self.fetch_emails(SPAM_LEARN, "spam")
        ham_emails = self.fetch_emails(HAM_LEARN, "ham")
        combined = spam_emails + ham_emails

        emails = [subject + " " + payload for _, _, subject, _, _, payload in combined]
        labels = [1 if email_type == "spam" else 0 for _, email_type, _, _, _, _ in combined]

        logging.info(f"Training data: {len(spam_emails)} spam, {len(ham_emails)} ham emails.")
        return emails, labels

    def _extract_payload(self, msg):
        """Extracts payload from an email message."""
        logging.debug("Extracting payload from message.")
        payload = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and part.get_payload(decode=True):
                    payload += part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            if msg.get_payload(decode=True):
                payload = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        return payload

    def start_postman(self):
        """Thread that processes incoming emails and classifies them."""
        logging.info("Starting postman thread to process incoming emails.")
        def postman():
            while self.running:
                # Wait for model updates
                logging.debug("Postman thread waiting for model updates.")
                self.model_updated.wait()
                self.model_updated.clear()
                
                with self.model_lock:
                    classifier = self.classifier
                    vectorizer = self.vectorizer

                logging.info(f"Postman thread processing emails in [{INBOX}]")
                mail = self.connect(INBOX)
                result, data = mail.search(None, "ALL")
                email_ids = data[0].split()

                for email_id in email_ids:
                    result, msg_data = mail.fetch(email_id, "(RFC822)")
                    if result == "OK":
                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = decode_email_header(msg.get("Subject", ""))
                        sender = decode_email_header(msg.get("From", ""))
                        recipient = decode_email_header(msg.get("To", ""))
                        payload = self._extract_payload(msg)

                        email_headers = {"subject": subject, "from": sender, "to": recipient}
                        classification = self.classify_email(payload, email_headers, classifier, vectorizer)

                        folder = SPAM_FOLDER if classification == 'spam' else HAM_FOLDER
                        logging.info(f"Moving email {email_id.decode()} to {folder}")
                        self.move(INBOX, folder, email_id)

                mail.close()
                mail.logout()
                time.sleep(SCAN_TIME)

        self.running = True
        threading.Thread(target=postman, daemon=True).start()

    def start_trainer(self):
        """Starts a thread to periodically retrain the model."""
        logging.info("Starting trainer thread for periodic model retraining.")
        def trainer():
            while self.running:
                logging.info("Trainer thread starting model retraining.")
                self.retrain_model()
                logging.info(f"Sleeping for {SCAN_TIME} seconds before next retrain.")
                time.sleep(SCAN_TIME)
        
        self.running = True
        threading.Thread(target=trainer, daemon=True).start()

    def classify_email(self, payload, headers, classifier, vectorizer):
        """Classifies an email using the loaded model."""
        logging.debug("Classifying email based on payload and headers.")
        full_text = f"{headers['subject']} {headers['from']} {headers['to']} {payload}"
        email_vector = vectorizer.transform([full_text])
        prediction = classifier.predict(email_vector)
        result = 'spam' if prediction[0] == 1 else 'ham'
        logging.info(f"Email classified as '{result}'.")
        return result

    def move(self, source_folder, destination_folder, email_id):
        """Moves an email from one folder to another."""
        logging.info(f"Moving email '{email_id.decode()}' from '{source_folder}' to '{destination_folder}'.")
        mail = self.connect(source_folder)
        result = mail.copy(email_id, destination_folder)
        if result[0] == "OK":
            mail.store(email_id, '+FLAGS', '\\Deleted')
            mail.expunge()
            logging.info(f"Email '{email_id.decode()}' moved successfully.")
        else:
            logging.error(f"Failed to move email '{email_id.decode()}'.")
        mail.close()
        mail.logout()

    def stop_threads(self):
        """Stops the postman thread."""
        logging.info("Stopping all threads.")
        self.running = False
        self.model_updated.set()


def main():

    logging.basicConfig(
        filename=LOG_FILE,  # Log file name
        level=getattr(logging, LOG_LEVEL, logging.INFO),     # Set logging level to INFO
        format='%(asctime)s %(threadName)s %(name)s[%(process)d]: %(levelname)s: %(message)s'
    )

    # Initialize PostOffice
    post_office = PostOffice()
    LogRotation = LogRotationThread()


    # Start the threads
    LogRotation.start()
    training_thread = post_office.start_trainer()
    processing_thread = post_office.start_postman()

    logging.info("Daemon threads for training, processing, LogRotation, started.")

    # Keep the main thread alive
    try:
        while True:
            pass
    except KeyboardInterrupt:
        logging.info("Stopping threads...")
        post_office.stop_threads()
        training_thread.join()
        processing_thread.join()
        logging.info("Threads stopped.")
        LogRotation.stop()

if __name__ == "__main__":
    main()
