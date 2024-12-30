import logging
import imaplib
import socket
import time
import email
import sys
import threading
import json
import hashlib
import os
from email.header import decode_header
from imaplib import IMAP4
from .config import config
from .utils import log_progress, load_failed_uids, save_failed_uids, interruptible_sleep, ElapsedTimeFormat
from .locks import failed_uid_lock

class Email:
    def __init__(self, raw_data):
        # msg_data is the result of an IMAP fetch command
        if not raw_data or not isinstance(raw_data, tuple):
            raise ValueError("Invalid raw_data format. Expected a tuple.")
        raw_email = raw_data[1]
        msg = email.message_from_bytes(raw_email)

        self.subject = self.get_subject(msg)
        self.sender = self.get_sender(msg)
        self.recipient = self.get_recipient(msg)
        self.payload = self.get_payload(msg)
        self.classification = None
        self.hash = EmailHasher.generate_sha256sum(raw_data[1])

    def get_subject(self, msg):
        # Extract subject from the message
        return self._decode_email_header(msg.get("Subject"))

    def get_sender(self, msg):
        return self._decode_email_header(msg.get("From"))

    def get_recipient(self, msg):
        return self._decode_email_header(msg.get("To"))

    def get_payload(self, msg):
        """
        Extract the email payload (body of the email).
        """
        if msg.is_multipart():
            # Combine all text/plain parts
            payload = []
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload.append(
                        part.get_payload(decode=True).decode(errors="ignore")
                    )
            return "\n".join(payload)
        else:
            # Single-part message
            payload = msg.get_payload(decode=True)
            return payload.decode("utf-8", errors="ignore") if payload else ""

    def __repr__(self):
        return f"Email(subject={self.subject}, sender={self.sender}, recipient={self.recipient}, uid={self.uid})"

    def _decode_email_header(self, header_value) -> str:
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

class PostOffice():
    def __init__(self, event: threading.Event):
        logging.info("Initializing PostOffice.")

        # Email settings
        self.email = config.EMAIL_ADDRESS
        self.password = config.PASSWORD
        self.url = config.IMAP_URL
        self.port = int(config.IMAP_PORT)
        self.inbox = config.INBOX
        self._StopEvent = event
        self.capabilities = None
        self._check_uidplus_support_()
        self._failed_uids = load_failed_uids()
        self.srv = None 

    def connect(self, max_retries: int = 5, retry_interval: int = 30) -> None:
        """Connects to the IMAP server and selects the mailbox."""
        logging.debug("Attempting to connect to the IMAP server.")
        attempts = 0
        while attempts < max_retries:
            try:
                self.srv = imaplib.IMAP4_SSL(self.url, self.port)
                self.srv.login(self.email, self.password)
                return
            except (socket.gaierror, IMAP4.error) as e:
                logging.error(f"IMAP connection error (attempt {attempts + 1}): {e}")
                interruptible_sleep(retry_interval,self._StopEvent)
                attempts += 1
        logging.critical("Max retries reached. Exiting...")
        sys.exit(1)

    def close(self):
        self.srv.close()
        logging.info("Mailbox closed.")

    def logout(self):
        self.srv.logout()
        logging.info("Logged out of IMAP server.")
    
    def select_box(self, mailbox: str, readonly: bool = True ):
        try:
            self.srv.select(mailbox, readonly) # DO NOT flag mail as read.
            logging.debug(f"Successfully connected to mailbox '{mailbox}'.")
        except IMAP4.error as e:
            logging.error(f"IMAP connection error selecting mailbox: {e}")

    def fetch_emails(self, mailbox: str) -> list[Email]:
        """Fetches emails from the specified mailbox."""
        self.srv.select(mailbox, readonly=True)
        result, data = self.srv.uid('search', None, "ALL")

        if result != "OK" or not data or not data[0]:
            logging.warning(f"No emails found in mailbox '{mailbox}'.")
            self.close()
            return []

        email_ids = data[0].split()
        email_objs = []
        # strip out the bad UIDs
        with failed_uid_lock:
            email_ids = [e for e in email_ids if (mailbox, e) not in self._failed_uids or e not in self._failed_uids[mailbox]]

        total_emails = len(email_ids)

        logging.info(f"Fetching ({total_emails}) emails from mailbox '{mailbox}'.")
        start_time = time.time()  # Record the start time for speed calculation

        for count, email_id in enumerate(email_ids, start=1):
            if self._StopEvent.is_set():
                logging.info("Stop signal received. Exiting")
                break

            retry_count = 3
            for attempt in range(retry_count):
                if self.capabilities and b"UIDPLUS" in self.capabilities:
                    # Fetch using UID if UIDPLUS is supported
                    fetch_command = "(RFC822)"
                    fetch_method = self.srv.uid
                    fetch_param = email_id  # UID-based fetch
                    log_identifier = f"UID {email_id}"
                else:
                    # Fetch using sequence number if UIDPLUS is not supported
                    fetch_command = "(RFC822)"
                    fetch_method = self.srv.fetch
                    fetch_param = email_id  # Sequence number-based fetch
                    log_identifier = f"sequence number {email_id}"

                logging.debug(f"Attempt {attempt + 1}/{retry_count}: Fetching email using {log_identifier} with command {fetch_command}.")

                try:
                    result, raw_imap_msg_data = fetch_method(fetch_param, fetch_command)

                    if result == "OK" and raw_imap_msg_data and raw_imap_msg_data[0]:
                        logging.debug(f"Successfully fetched email using {log_identifier}.")
                        break  # Exit loop on successful fetch
                except Exception as e:
                    logging.error(f"Error during email fetch attempt {attempt + 1}: {e}", exc_info=True)

                time.sleep(2)  # Wait 2 seconds before retrying
            else:
                logging.error(f"Failed to fetch email UID {email_id} after {retry_count} attempts: {raw_imap_msg_data}")
                if mailbox not in self._failed_uids:
                    self._failed_uids[mailbox] = set()
                self._failed_uids[mailbox].add(email_id.decode('utf-8'))

            # log progress after fetch
            if count % 100 == 0 or count == total_emails:
                log_progress(count, total_emails, start_time)

            if not isinstance(raw_imap_msg_data[0], tuple):
                logging.error(f"Invalid data format for email UID {email_id}. Expected a tuple but got: {type(raw_imap_msg_data[0])}")
                continue

            if result != "OK":
                logging.warning(f"Fetch result for email UID {email_id} was not 'OK'. Result: {result}")
                continue

            try:
                email_obj = Email(raw_imap_msg_data[0])  # Pass the tuple to the Email object
                email_objs.append(email_obj)
            except (TypeError, ValueError) as e:
                logging.error(f"Error processing email UID {email_id}: {e}")
                logging.debug(f"Raw message data: {raw_imap_msg_data}")

        logging.info(f"Fetched {len(email_objs)} emails from mailbox '{mailbox}'. Time elapsed: {ElapsedTimeFormat(start_time, time.time())}")
        save_failed_uids(self._failed_uids)
        self.srv.close()
        return email_objs

    def move(self, source_folder: str, destination_folder: str, email_id: str):
        """Moves a single email from one folder to another."""
        logging.debug(f"Moving email '{int(email_id)}' from '{source_folder}' to '{destination_folder}'.")
        self.select_box(source_folder, readonly=False)

        if self.capabilities and b"UIDPLUS" in self.capabilities:
            logging.debug(f"Moving email UID {email_id} to {destination_folder} with UIDPLUS support.")
            result = self.srv.uid('COPY', email_id.decode(), destination_folder)
        else:
            logging.debug(f"Moving email UID {email_id} to {destination_folder} without UIDPLUS support.")
            result = self.srv.copy(email_id.decode(), destination_folder)

        if result[0] == "OK":
            self.srv.store(str(email_id), '+FLAGS', '\\Deleted')
            self.srv.expunge()
            logging.debug(f"Email '{int(email_id)}' moved successfully.")
        else:
            logging.error(f"Failed to move email '{int(email_id)}'.")
        self.srv.close()

    def bulk_move(self, source_folder: str, destination_folder: str, email_ids: list[str]):
        """
        Moves multiple emails from one folder to another in bulk.

        Parameters:
        - source_folder: The folder to move emails from.
        - destination_folder: The folder to move emails to.
        - email_ids: A list of email UIDs as strings.
        """
        try:
            logging.debug(f"Starting bulk move of {len(email_ids)} emails from '{source_folder}' to '{destination_folder}'.")

            # Ensure email IDs are strings for IMAP operations
            email_ids_str = ",".join(uid.decode() if isinstance(uid, bytes) else uid for uid in email_ids)

            # Select source folder
            self.select_box(source_folder, readonly=False)

            # Copy emails to destination folder
            result, copy_response = self.srv.uid('COPY', email_ids_str, destination_folder)
            if result != "OK":
                raise IMAP4.error(f"Failed to copy emails to '{destination_folder}': {copy_response}")
            logging.debug(f"Copied {len(email_ids)} emails to '{destination_folder}' successfully.")

            # Mark emails as deleted in source folder
            result, store_response = self.srv.uid("STORE", email_ids_str, "+FLAGS", "(\\Deleted)")
            if result != "OK":
                raise IMAP4.error(f"Failed to mark emails as deleted: {store_response}")
            logging.debug(f"Marked {len(email_ids)} emails as deleted in '{source_folder}'.")

            # Expunge to permanently delete emails
            self.srv.expunge()
            logging.info(f"Bulk move completed: {len(email_ids)} emails moved from '{source_folder}' to '{destination_folder}'.")

        except IMAP4.error as e:
            logging.error(f"IMAP error during bulk move: {e}")
            raise

        except Exception as e:
            logging.error(f"Unexpected error during bulk move: {e}")
            raise

        finally:
            self.close()

    def _check_uidplus_support_(self) -> bool:
        """Check if the IMAP server supports UIDPLUS (RFC 4315)."""
        try:
            self.connect()

            # Query the server capabilities
            status, capabilities = self.srv.capability()
            if status == "OK":
                self.capabilities = capabilities  # Save capabilities as an attribute
                logging.debug(f"Server Capabilities: {capabilities}")
                if b"UIDPLUS" in capabilities:
                    logging.info("The server supports UIDPLUS (RFC 4315).")
                    uidplus_supported = True
                else:
                    logging.warning("UIDPLUS is not supported by the server.")
                    uidplus_supported = False
            else:
                logging.error("Failed to retrieve server capabilities.")
                uidplus_supported = False

            logging.info("Logged out from the IMAP server.")

            return uidplus_supported

        except imaplib.IMAP4.error as e:
            logging.critical(f"IMAP4 error: {e}")
        except Exception as e:
            logging.critical(f"Unexpected error: {e}")
        return False
    
class EmailHasher:
    def __init__(self, table_file='email_hash_table.json', lock=None):
        self.table_file = f"{config.TRAINING_DATA_PATH}/{table_file}"
        self.lock = lock or threading.RLock()  # Use the provided lock or create a new one

        # Load the existing table from disk if it exists
        if os.path.exists(self.table_file):
            with open(self.table_file, 'r') as f:
                self.hash_table = json.load(f)
        else:
            self.hash_table = {}

    def save_hash_table(self):
        """
        Save the hash table to disk in JSON format.
        """
        with self.lock:  # Acquire the lock before writing
            with open(self.table_file, 'w') as f:
                json.dump(self.hash_table, f, indent=4)

    def load_hash_table(self):
        """
        Load the hash table from disk if the file exists.
        """
        with self.lock:  # Acquire the lock before reading
            if os.path.exists(self.table_file):
                with open(self.table_file, 'r') as f:
                    self.hash_table = json.load(f)
            else:
                self.hash_table = {}

    def add_email(self, email_hash, classification_number):
        """
        Add an email hash and its classification to the hash table.
        """
        with self.lock:  # Acquire the lock before modifying the hash table
            self.hash_table[email_hash] = classification_number
            self.save_hash_table()

    def get_classification(self, email_content):
        """
        Get the classification number for an email hash.
        """
        email_hash = self.generate_sha256sum(email_content)
        return self.hash_table.get(email_hash, None)

    @staticmethod
    def generate_sha256sum(email_content) -> str:
        """
        Generate a SHA-256 hash from the email content.
        """
        if isinstance(email_content, str):
            email_content = email_content.encode('utf-8')
        sha256_hash = hashlib.sha256(email_content).hexdigest()
        return sha256_hash

    