import logging
import imaplib
import socket
import time
import email
import sys
import threading
from email.header import decode_header
from .config import config

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
        result, data = mail.search(None, "ALL")
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
                elapsed_time = time.time() - start_time
                emails_per_second = count / elapsed_time if elapsed_time > 0 else 0
                remaining_emails = total_emails - count
                estimated_time_remaining = (
                    remaining_emails / emails_per_second if emails_per_second > 0 else float('inf')
                )
                etc_formatted = time.strftime(
                    "%H:%M:%S", time.gmtime(estimated_time_remaining)
                )

                logging.info(
                    f"Progress: {count}/{total_emails} emails fetched "
                    f"({emails_per_second:.2f} emails/s) Estimated time to completion: {etc_formatted}"
                )
                
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
        """Moves an email from one folder to another."""
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
