import logging
import imaplib
import socket
import time
import email
import sys
import threading
from email.header import decode_header
from imaplib import IMAP4
from .config import config
from .helper import log_progress, load_failed_uids, save_failed_uids, interruptible_sleep, ElapsedTimeFormat
from .locks import failed_uid_lock

class Email:
    def __init__(self, uid, raw_data):
        # msg_data is the result of an IMAP fetch command
        if not raw_data or not isinstance(raw_data, tuple):
            raise ValueError("Invalid raw_data format. Expected a tuple.")
        raw_email = raw_data[1]
        msg = email.message_from_bytes(raw_email)

        self.subject = self.get_subject(msg)
        self.sender = self.get_sender(msg)
        self.recipient = self.get_recipient(msg)
        self.payload = self.get_payload(msg)
        self.uid = uid
        self.classification = None

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
        self.check_uidplus_support()
        self._failed_uids = load_failed_uids()

    def connect(self, mailbox: str, max_retries: int = 5, retry_interval: int = 30) -> imaplib.IMAP4_SSL:
        """Connects to the IMAP server and selects the mailbox."""
        logging.debug(f"Attempting to connect to the IMAP server and access mailbox '{mailbox}'.")
        mail = None
        attempts = 0
        while attempts < max_retries:
            try:
                mail = imaplib.IMAP4_SSL(self.url, self.port)
                mail.login(self.email, self.password)
                mail.select(mailbox, readonly=True) # DO NOT flag mail as read.
                logging.debug(f"Successfully connected to mailbox '{mailbox}'.")
                return mail
            except (socket.gaierror, imaplib.IMAP4.error) as e:
                logging.error(f"IMAP connection error (attempt {attempts + 1}): {e}")
                interruptible_sleep(retry_interval,self._StopEvent)
                attempts += 1
        logging.critical("Max retries reached. Exiting...")
        sys.exit(1)

    def fetch_emails(self, mailbox: str) -> list[Email]:
        """Fetches emails from the specified mailbox."""
        mail = self.connect(mailbox)
        result, data = mail.uid('search', None, "ALL")

        if result != "OK" or not data or not data[0]:
            logging.warning(f"No emails found in mailbox '{mailbox}'.")
            mail.close()
            mail.logout()
            return []

        email_ids = data[0].split()
        email_objs = []
        total_emails = len(email_ids)
        # strip out the bad UIDs
        with failed_uid_lock:
            email_ids = [e for e in email_ids if (mailbox, e.decode('utf-8')) not in self._failed_uids]

        logging.info(f"Fetching ({total_emails}) emails from mailbox '{mailbox}'.")
        start_time = time.time()  # Record the start time for speed calculation

        for count, email_id in enumerate(email_ids, start=1):
            if self._StopEvent.is_set():
                logging.info("Stop signal received. Exiting")
                break

            retry_count = 3
            for attempt in range(retry_count):
                fetch_command = "(UID RFC822)" if self.capabilities and b"UIDPLUS" in self.capabilities else "(RFC822)"
                logging.debug(f"Attempt {attempt + 1}/{retry_count}: Fetching email using UID {email_id} with command {fetch_command}.")
                result, raw_imap_msg_data = mail.fetch(email_id, fetch_command)

                if result == "OK" and raw_imap_msg_data and raw_imap_msg_data[0]:
                    break  # Exit loop on successful fetch
                time.sleep(2)  # Wait 2 seconds before retrying
            # log progress after fetch
            if count % 100 == 0 or count == total_emails:
                log_progress(count, total_emails, start_time)

            if not raw_imap_msg_data or raw_imap_msg_data[0] is None:
                logging.error(f"Failed to fetch email UID {email_id} after {retry_count} attempts: {raw_imap_msg_data}")
                self._failed_uids.add((mailbox, email_id.decode('utf-8')))
                continue

            if not isinstance(raw_imap_msg_data[0], tuple):
                logging.error(f"Invalid data format for email UID {email_id}. Expected a tuple but got: {type(raw_imap_msg_data[0])}")
                continue

            if result != "OK":
                logging.warning(f"Fetch result for email UID {email_id} was not 'OK'. Result: {result}")
                continue

            try:
                email_obj = Email(email_id, raw_imap_msg_data[0])  # Pass the tuple to the Email object
                email_objs.append(email_obj)
            except (TypeError, ValueError) as e:
                logging.error(f"Error processing email UID {email_id}: {e}")
                logging.debug(f"Raw message data: {raw_imap_msg_data}")

        logging.info(f"Fetched {len(email_objs)} emails from mailbox '{mailbox}'. Time elapsed: {ElapsedTimeFormat(start_time, time.time())}")
        save_failed_uids(self._failed_uids)
        mail.close()
        mail.logout()
        return email_objs

    def move(self, source_folder, destination_folder, email_id: str):
        """Moves a single email from one folder to another."""
        logging.debug(f"Moving email '{int(email_id)}' from '{source_folder}' to '{destination_folder}'.")
        mail = self.connect(source_folder)

        if self.capabilities and b"UIDPLUS" in self.capabilities:
            logging.debug(f"Moving email UID {email_id} to {destination_folder} with UIDPLUS support.")
            result = mail.uid('COPY', email_id.decode(), destination_folder)
        else:
            logging.debug(f"Moving email UID {email_id} to {destination_folder} without UIDPLUS support.")
            result = mail.copy(email_id.decode(), destination_folder)

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
        try:
            logging.debug(f"Starting bulk move of {len(email_ids)} emails from '{source_folder}' to '{destination_folder}'.")

            # Ensure email IDs are strings for IMAP operations
            email_ids_str = ",".join(uid.decode() for uid in email_ids if isinstance(uid, bytes))

            # Connect to the source folder
            mail = self.connect(source_folder)

            try:
                # Copy emails to the destination folder
                if self.capabilities and b"UIDPLUS" in self.capabilities:
                    logging.debug(f"Moving email UID {email_ids} to {destination_folder} with UIDPLUS support.")
                    result, copy_response = mail.uid('COPY', email_ids_str, destination_folder)
                else:
                    logging.debug(f"Moving email UID {email_ids} to {destination_folder} without UIDPLUS support.")
                    result, copy_response = mail.copy(email_ids_str, destination_folder)

                if result != "OK":
                    logging.error(f"Failed to copy emails to '{destination_folder}': {copy_response}")
                    raise IMAP4.error(f"COPY command failed: {copy_response}")

                logging.debug(f"Copied {len(email_ids)} emails to '{destination_folder}' successfully.")

                # Mark emails as deleted in the source folder
                result, store_response = mail.uid("STORE", email_ids_str, "+FLAGS", "(\\Deleted)")
                if result != "OK":
                    logging.error(f"Failed to mark emails as deleted: {store_response}")
                    raise IMAP4.error(f"STORE command failed: {store_response}")

                logging.debug(f"Marked {len(email_ids)} emails as deleted in '{source_folder}'.")

                # Expunge to permanently delete emails from the source folder
                try:
                    mail.expunge()
                    logging.info(f"Bulk move completed: {len(email_ids)} emails moved from '{source_folder}' to '{destination_folder}'.")
                except IMAP4.error as e:
                    logging.error(f"Failed to expunge emails: {e}")
                    raise

            except IMAP4.error as e:
                logging.error(f"IMAP error during bulk move operations: {e}")
                raise
            except Exception as e:
                logging.error(f"Unexpected error during bulk move operations: {e}")
                raise

        except IMAP4.error as e:
            logging.error(f"IMAP error during bulk move: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during bulk move: {e}")
        finally:
            try:
                if 'mail' in locals() and mail is not None:
                    mail.close()
                    mail.logout()
                    logging.debug("Connection to the mail server closed and logged out.")
            except Exception as e:
                logging.error(f"Error closing or logging out from the mail server: {e}")

    def check_uidplus_support(self):
        """Check if the IMAP server supports UIDPLUS (RFC 4315)."""
        try:
            mail = self.connect(self.inbox)

            # Query the server capabilities
            status, capabilities = mail.capability()
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

            # Logout from the server
            mail.close()
            mail.logout()
            logging.info("Logged out from the IMAP server.")

            return uidplus_supported

        except imaplib.IMAP4.error as e:
            logging.critical(f"IMAP4 error: {e}")
        except Exception as e:
            logging.critical(f"Unexpected error: {e}")

        return False
