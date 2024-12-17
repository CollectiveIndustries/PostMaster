

from email.header import decode_header
import joblib
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
import configparser
import email
import imaplib
import logging
import socket
import sys
import threading
import time


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


class PostOffice:
    def __init__(self, config_file="config.ini"):
        # Load configuration
        config = configparser.ConfigParser()
        config.read(config_file)

        # Email settings
        self.email = config.get('EmailSettings', 'email_address')
        self.password = config.get('EmailSettings', 'password')
        self.url = config.get('ConnectionSettings', 'url')
        self.port = int(config.get('ConnectionSettings', 'port'))
        self.inbox = config.get('Folders', 'inbox')

        # Folder settings
        self.spam_folder = config.get('Folders', 'spam_folder')
        self.ham_folder = config.get('Folders', 'ham_folder')
        self.infected_folder = config.get('Folders', 'infected_folder')
        self.spam_learn = config.get('Folders', 'spam_learn')
        self.ham_learn = config.get('Folders', 'ham_learn')

        self.TrainingDataPath = config.get('DaemonSettings', 'data_path')
        self.ScanTime = int(config.get('DaemonSettings', 'scan_time'))

        self.LogFile = config.get('DaemonSettings', 'log_file')
        self.log_level = config.get('DaemonSettings', 'log_level', fallback="INFO").upper()

        self.classifier = None
        self.vectorizer = None

        self.model_file = f"{self.TrainingDataPath}/naive_bayes_classifier.pkl"
        self.vectorizer_file = f"{self.TrainingDataPath}/vectorizer.pkl"

        # Synchronization lock for threading
        self.lock = threading.RLock()
        self.load_model()
        logging.basicConfig(
            filename=self.LogFile,  # Log file name
            level=getattr(logging, self.log_level, logging.INFO),     # Set logging level to INFO
            format='%(asctime)s %(threadName)s %(name)s[%(process)d]: %(levelname)s: %(message)s'
        )

    def load_model(self):
        """Loads the model and vectorizer from disk."""
        try:
            with self.lock:
                self.classifier = joblib.load(self.model_file)
                self.vectorizer = joblib.load(self.vectorizer_file)
            logging.info("Model and vectorizer loaded successfully.")
        except FileNotFoundError:
            logging.error("Model or vectorizer file not found. Fetching Data from IMAP")
            self.retrain_model(self.model_file,self.vectorizer_file)

    def connect(self, mailbox, max_retries=5, retry_interval=30):
        """
        Tries to connect to the IMAP server and select the given mailbox with retry logic.
        Args:
        - mailbox: Mailbox to select
        - max_retries: Maximum number of retry attempts
        - retry_interval: Time to wait between retries (in seconds)
        Returns:
        - mail: IMAP connection object if successful, None if failed after max retries
        """
        mail = None
        attempts = 0
        while attempts < max_retries:
            try:
                mail = imaplib.IMAP4_SSL(self.url, self.port)
                mail.login(self.email, self.password)
                mail.select(mailbox)
                break  # Successful connection, exit loop
            except socket.gaierror as e:
                logging.error(f"Temporary failure in name resolution (attempt {attempts + 1}): {e}")
            except imaplib.IMAP4.error as e:
                logging.error(f"IMAP error (attempt {attempts + 1}): {e}")
            except Exception as e:
                logging.error(f"An unexpected error occurred (attempt {attempts + 1}): {e}")
            finally:
                logging.debug(f"Mailbox ({mailbox}) selected.")
            attempts += 1
            if attempts < max_retries:
                logging.info(f"Retrying in {retry_interval} seconds...")
                time.sleep(retry_interval)
            else:
                logging.error("Max retries reached. Connection failed.")
        if mail is None:
            logging.error("Failed to establish mail connection after max retries. Exiting...")
            sys.exit(1)  # Exiting with a status code of 1 indicating failure
        return mail

    def fetch_emails(self, mailbox, email_type):
        mail = self.connect(mailbox)
        result, data = mail.search(None, "ALL")
        email_ids = data[0].split()

        for email_id in email_ids:
            logging.debug(f"Fetching email ID: {email_id.decode()} ({email_type})")
            result, msg_data = mail.fetch(email_id, "(RFC822)")
            if result == "OK":
                logging.debug("Message retrieved, decoding")
                msg = email.message_from_bytes(msg_data[0][1])

                # Decode headers
                subject = decode_email_header(msg.get("Subject", ""))
                sender = decode_email_header(msg.get("From", ""))
                recipient = decode_email_header(msg.get("To", ""))

                # Extract payload
                payload = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain" and part.get_payload(decode=True):
                            payload += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                else:
                    if msg.get_payload(decode=True):
                        payload = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

                # Store email with id, type, headers, and contents
                logging.debug("Waiting for email lock.....")
                with self.lock:
                    logging.debug("Storing message")
                    self.emails[email_id.decode()] = {
                        "type": email_type,
                        "headers": {
                            "subject": subject,
                            "from": sender,
                            "to": recipient
                        },
                        "contents": payload
                    }

        logging.debug("Closing connection and logging out of IMAP server")
        mail.close()
        mail.logout()

    def _fetch_training_data(self):
        # Fetch emails and populate self.emails dictionary
        logging.debug("Loading training Data (spam/ham) from IMAP server")
        self.fetch_emails(self.spam_learn, "spam")
        self.fetch_emails(self.ham_learn, "ham")

        # Move spam and ham emails to their respective folders
        # The spam_learn and ham_learn folders should be used as a que once processed
        # data is moved out as the model is already built
        for email_id, email_data in self.emails.items():
            if email_data["type"] == "spam":
                logging.debug(f"Moving email {email_id} to spam folder")
                self.move(self.spam_learn, self.spam_folder, email_id)
            else:
                logging.debug(f"Moving email {email_id} to ham folder")
                self.move(self.ham_learn, self.ham_folder, email_id)

        # Extract emails and labels for training
        emails = [
            email_data["headers"]["subject"] + " " + email_data["contents"]
            for email_data in self.emails.values()
        ]
        labels = [1 if email_data["type"] == "spam" else 0 for email_data in self.emails.values()]

        return emails, labels

    def retrain_model(self):
        """Retrains the model with new data and saves it."""
        # Load training data
        emails, labels = self._fetch_training_data()
        
        # Vectorize email text
        vectorizer = CountVectorizer()
        X = vectorizer.fit_transform(emails)

        # Train the model
        classifier = MultinomialNB()
        classifier.fit(X, labels)

        # Save updated model and vectorizer
        with self.lock:
            joblib.dump(classifier, self.model_file)
            joblib.dump(vectorizer, self.vectorizer_file)
            logging.info("Model and vectorizer updated and saved.")

        # Notify postman thread that model has been updated
        self.model_updated.set()

    def classify_email(self, email_content, email_headers, classifier, vectorizer):
        """Classifies a single email based on the trained model."""
        # Combine headers and content into a single string for classification
        logging.debug(f"Running email classifier: Subject: [{email_headers['subject']}]")
        full_email_text = f"{email_headers['subject']} {email_headers['from']} {email_headers['to']} {email_content}"
        email_vector = vectorizer.transform([full_email_text])
        prediction = classifier.predict(email_vector)
        return 'spam' if prediction[0] == 1 else 'ham'

    def start_trainer(self):
        """Runs periodic retraining in a separate thread."""
        def trainer():
            while True:
                logging.debug("Waiting for the next interval...")
                time.sleep(self.ScanTime)
                logging.debug("Checking for new training data...")
                with self.lock: # BUG: Thread locking and prevents the scanner from running while its retraining.
                    self.retrain_model(self.model_file, self.vectorizer_file)

        thread = threading.Thread(target=trainer, daemon=True)
        thread.start()

    def start_postman(self):
        """Processes emails in the inbox and classifies them in a separate thread."""
        def postman():
            while self.running:
                # Load the latest model and vectorizer
                with self.lock:
                    classifier = joblib.load(self.model_file)
                    vectorizer = joblib.load(self.vectorizer_file)
                    mail = self.connect(self.inbox)

                result, data = mail.search(None, "ALL")
                email_ids = data[0].split()

                for email_id in email_ids:
                    logging.info(f"Processing email ID: {email_id.decode()} of {len(email_ids)}")
                    result, msg_data = mail.fetch(email_id, "(RFC822)")
                    if result == "OK":
                        msg = email.message_from_bytes(msg_data[0][1])

                        # Decode headers
                        subject = decode_email_header(msg.get("Subject", ""))
                        sender = decode_email_header(msg.get("From", ""))
                        recipient = decode_email_header(msg.get("To", ""))

                        # Extract payload
                        payload = self._extract_payload(msg)

                        # Classify the email
                        email_headers = {"subject": subject, "from": sender, "to": recipient}
                        classification = self.classify_email(payload, email_headers, classifier, vectorizer)

                        # Move email based on classification
                        if classification == 'spam':
                            logging.info(f"Moving email: {email_id} from {self.inbox} to {self.spam_folder}")
                            self.move(self.inbox, self.spam_folder, email_id)
                        else:
                            logging.info(f"Moving email: {email_id} from {self.inbox} to {self.ham_folder}")
                            self.move(self.inbox, self.ham_folder, email_id)

                logging.debug("Closing connection and logging out of IMAP server")
                mail.close()
                mail.logout()

                # Wait before reprocessing
                time.sleep(self.ScanTime)

        thread = threading.Thread(target=postman, daemon=True)
        self.running = True
        thread.start()

    def _extract_payload(self, msg):
        payload = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and part.get_payload(decode=True):
                    payload += part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            if msg.get_payload(decode=True):
                payload = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        return payload

    def move(self, source_folder, destination_folder, email_id):
        """Moves an email from one folder to another."""
        with self.lock:
            mail = self.connect(source_folder)

            # Copy email to the destination folder
            result = mail.copy(email_id, destination_folder)
            if result[0] == "OK":
                # Mark the email as deleted in the source folder
                mail.store(email_id, '+FLAGS', '\\Deleted')
                logging.debug("Email stored.")
                mail.expunge()
            else:
                logging.error(f"Failed to move email {email_id} from {source_folder} to {destination_folder}")

            mail.close()
            mail.logout()

    def stop_threads(self):
        """Stops all running threads."""
        self.running = False