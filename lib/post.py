import logging
import imaplib
import socket
import time
import email
import sys
import threading
from email.header import decode_header
from .config import config
from .helper import log_progress

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

    def connect(self, mailbox: str, max_retries: int = 5, retry_interval: int = 30):
        """Connects to the IMAP server and selects the mailbox."""
        logging.debug(f"Attempting to connect to the IMAP server and access mailbox '{mailbox}'.")
        mail = None
        attempts = 0
        while attempts < max_retries:
            try:
                mail = imaplib.IMAP4_SSL(self.url, self.port)
                mail.login(self.email, self.password)
                mail.select(mailbox)
                logging.debug(f"Successfully connected to mailbox '{mailbox}'.")
                return mail
            except (socket.gaierror, imaplib.IMAP4.error) as e:
                logging.error(f"IMAP connection error (attempt {attempts + 1}): {e}")
                time.sleep(retry_interval)
                attempts += 1
        logging.critical("Max retries reached. Exiting...")
        sys.exit(1)

    def fetch_emails(self, mailbox: str) -> list:
        """Fetches emails from the specified mailbox."""
        mail = self.connect(mailbox)
        result, data = mail.uid('search', None, "ALL")
        email_ids = data[0].split()
        emails = []
        total_emails = len(email_ids)

        logging.info(f"Fetching ({total_emails}) emails from mailbox '{mailbox}'.")
        start_time = time.time()  # Record the start time for speed calculation
        for count, email_id in enumerate(email_ids, start=1):
            if self._StopEvent.is_set():
                logging.info("Stop signal received. Exiting")
                return
            result, msg_data = mail.fetch(email_id, "(RFC822)")
            if result == "OK":
                msg = email.message_from_bytes(msg_data[0][1])
                subject = self._decode_email_header(msg.get("Subject", ""))
                sender = self._decode_email_header(msg.get("From", ""))
                recipient = self._decode_email_header(msg.get("To", ""))
                payload = self._extract_payload(msg)

                emails.append((email_id.decode(), subject, sender, recipient, payload))
            # Log progress every 100 emails
            if count % 100 == 0 or count == total_emails:
               log_progress(count,total_emails,start_time)
                
        logging.info(f"Fetched {len(emails)} emails from mailbox '{mailbox}'.")
        mail.close()
        mail.logout()
        return emails

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

    def move(self, source_folder, destination_folder, email_id: str):
        """Moves a single email from one folder to another."""
        logging.debug(f"Moving email '{int(email_id)}' from '{source_folder}' to '{destination_folder}'.")
        mail = self.connect(source_folder)
        result = mail.copy(str(email_id), destination_folder)
        if result[0] == "OK":
            mail.store(str(email_id), '+FLAGS', '\\Deleted')
            mail.expunge()
            logging.debug(f"Email '{int(email_id)}' moved successfully.")
        else:
            logging.error(f"Failed to move email '{int(email_id)}'.")
        mail.close()
        mail.logout()

    def bulk_move(self, source_folder, destination_folder, email_ids: list):
        """Moves multiple emails from one folder to another in bulk."""
        logging.debug(f"Starting bulk move of {len(email_ids)} emails from '{source_folder}' to '{destination_folder}'.")

        # Ensure email IDs are strings for IMAP operations
        email_ids_str = ",".join(map(str, email_ids))

        # Connect to the source folder
        mail = self.connect(source_folder)

        # Copy emails to the destination folder
        result, copy_response = mail.uid("COPY", email_ids_str, destination_folder)
        if result == "OK":
            logging.debug(f"Copied {len(email_ids)} emails to '{destination_folder}' successfully.")

            # Mark emails as deleted in the source folder
            result, store_response = mail.uid("STORE", email_ids_str, "+FLAGS", "(\\Deleted)")
            if result == "OK":
                logging.debug(f"Marked {len(email_ids)} emails as deleted in '{source_folder}'.")

                # Expunge to permanently delete emails from the source folder
                mail.expunge()
                logging.info(f"Bulk move completed: {len(email_ids)} emails moved from '{source_folder}' to '{destination_folder}'.")
            else:
                logging.error(f"Failed to mark emails as deleted: {store_response}")
        else:
            logging.error(f"Failed to copy emails to '{destination_folder}': {copy_response}")

        # Close and logout
        mail.close()
        mail.logout()

    def _decode_email_header(self, header_value):
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


class Email:
    """
    A class representing an email with attributes for subject, sender, recipient, and payload.
    """
    def __init__(self, subject, sender, recipient, payload):
        """
        Initialize an Email object.

        :param subject: The subject of the email
        :param sender: The sender of the email
        :param recipient: The recipient of the email
        :param payload: The body or content of the email
        """
        self.subject = subject
        self.sender = sender
        self.recipient = recipient
        self.payload = payload

    def __repr__(self):
        """
        Return a string representation of the Email object for debugging.
        """
        return (
            f"Email(subject={self.subject!r}, sender={self.sender!r}, "
            f"recipient={self.recipient!r}, payload={len(self.payload)} characters)"
        )

    def to_string(self, include_subject=True, include_sender=True, include_recipient=False, include_payload=True):
        """
        Convert the email object to a formatted string based on included fields.

        :param include_subject: Whether to include the subject in the string
        :param include_sender: Whether to include the sender in the string
        :param include_recipient: Whether to include the recipient in the string
        :param include_payload: Whether to include the payload in the string
        :return: A formatted string representation of the email
        """
        components = []
        if include_subject:
            components.append(self.subject)
        if include_sender:
            components.append(self.sender)
        if include_recipient:
            components.append(self.recipient)
        if include_payload:
            components.append(self.payload)
        return " ".join(components)
