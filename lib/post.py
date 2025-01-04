import logging
import imaplib
import time
import email
import threading
import hashlib
import re
from typing import Generator
from email.header import decode_header
from imaplib import IMAP4
from .config import config
from .utils import log_progress
from .database import EmailDatabase

class Email:
    def __init__(self, raw_data: tuple):
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
        self.X_GM_MSGID, self.msg_sequence, self.email_size = self.extract_message_parts(raw_data[0])
        self.hash = EmailHasher.generate_sha256sum(raw_data[1])

    def extract_message_parts(self, raw_msg_data):
        """Extracts X-GM-MSGID, message sequence number, and email size using regular expressions."""
        # Define regex patterns for extracting the parts
        msgid_pattern = rb"X-GM-MSGID (\d+)"
        sequence_pattern = rb"^(\d+)"
        size_pattern = rb"{(\d+)}"

        msgid = None
        msg_sequence = None
        email_size = None

        try:
            # Search for the X-GM-MSGID
            msgid_match = re.search(msgid_pattern, raw_msg_data)
            if msgid_match:
                msgid = msgid_match.group(1).decode('utf-8')

            # Search for the message sequence number
            sequence_match = re.search(sequence_pattern, raw_msg_data)
            if sequence_match:
                msg_sequence = sequence_match.group(1).decode('utf-8')

            # Search for the email size
            size_match = re.search(size_pattern, raw_msg_data)
            if size_match:
                email_size = size_match.group(1).decode('utf-8')

            logging.debug(f"Extracted X-GM-MSGID: {msgid}, Sequence: {msg_sequence}, Size: {email_size}")
        except Exception as e:
            logging.error(f"Error extracting message parts: {e}")
        
        return msgid, msg_sequence, email_size

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
    def __init__(self, event: threading.Event, mailbox: str):
        logging.info("Initializing PostOffice.")

        # Email settings
        self.email = config.EMAIL_ADDRESS
        self.password = config.PASSWORD
        self.url = config.IMAP_URL
        self.port = int(config.IMAP_PORT)
        self._StopEvent = event
        self.capabilities = None
        self._check_uidplus_support_()
        self.srv = None
        self.mailbox = mailbox
        self.database = EmailDatabase()

    def connect(self):
        """
        Establish a connection to the IMAP server.
        """
        try:
            self.srv = imaplib.IMAP4_SSL(self.url, self.port)
            self.srv.login(self.email, self.password)
            logging.info(f"Connected to IMAP server {self.url} on port {self.port}.")
        except Exception as e:
            self.srv = None  # Ensure srv is reset to None on failure
            logging.error(f"Failed to connect to IMAP server: {e}", exc_info=True)
            raise

    def close(self):
        try:
            # Check if the server state is 'SELECTED'
            if self.srv.state == 'SELECTED':
                self.srv.close()
                logging.info("Mailbox closed successfully.")
            else:
                logging.warning(f"Cannot close mailbox. Current state: {self.srv.state}. Expected: 'SELECTED'.")
        except Exception as e:
            logging.error(f"Error while closing the mailbox: {e}", exc_info=True)

    def logout(self):
        self.srv.logout()
        logging.info("Logged out of IMAP server.")

    def reconnect(self):
        """
        Ensure the IMAP connection is active and in the correct state.
        Reconnect and re-select the folder if necessary.
        """
        try:
            # Check if the connection is active
            if self.srv is None or self.srv.state not in ['SELECTED', 'AUTH']:
                logging.warning(f"IMAP connection is in state '{self.srv.state if self.srv else 'None'}'. Reconnecting...")
                self.connect()

            # Check if the folder is selected
            if self.srv.state != 'SELECTED':
                self.srv.select(self.mailbox)  # Ensure the correct folder is selected
                logging.info(f"Folder '{self.mailbox}' selected successfully.")
                return True
        except imaplib.IMAP4.error as e:
            logging.error(f"Failed to reconnect or select folder '{self.mailbox}': {e}")
            return False

    def select_box(self, readonly: bool = True ):
        try:
            self.srv.select(self.mailbox, readonly) # DO NOT flag mail as read.
            logging.debug(f"Successfully connected to mailbox '{self.mailbox}'.")
        except IMAP4.error as e:
            logging.error(f"IMAP connection error selecting mailbox: {e}")

    def fetch_batch(self, x_gm_msgids: list[int]) -> Generator[Email, None, None]:
        """Fetches emails based on provided x_gm_msgid list."""
        total_emails = len(x_gm_msgids)
        logging.info(f"Fetching ({total_emails}) emails from x_gm_msgid list.")
        start_time = time.time()

        for count, x_gm_msgid in enumerate(x_gm_msgids, start=1):
            if self._StopEvent.is_set():
                logging.info("Stop signal received. Exiting batch fetch.")
                return

            retry_count = 3
            for attempt in range(retry_count):
                logging.debug(f"Attempt {attempt + 1}/{retry_count}: Fetching email with X-GM-MSGID {x_gm_msgid}.")
                try:
                    # Convert x_gm_msgid to string as required by IMAP fetch
                    self.reconnect()
                    status, data = self.srv.search(None, f'X-GM-MSGID {x_gm_msgid}')
                    if status != "OK" or not data or not data[0]:
                        logging.debug(f"Email with X-GM-MSGID {x_gm_msgid} not found.")
                        continue
                    uid = data[0].split()[0]
                    result, raw_imap_msg_data = self.srv.fetch(uid, "(RFC822)")

                    if result == "OK" and raw_imap_msg_data and raw_imap_msg_data[0]:
                        logging.debug(f"Successfully fetched email with X-GM-MSGID {x_gm_msgid}.")
                        break
                except Exception as e:
                    logging.error(f"Error during email fetch attempt {attempt + 1}: {e}", exc_info=True)
                time.sleep(2)
            else:
                logging.error(f"Failed to fetch email with X-GM-MSGID {x_gm_msgid} after {retry_count} attempts.")
                continue

            if not isinstance(raw_imap_msg_data[0], tuple):
                logging.error(f"Invalid data format for email with X-GM-MSGID {x_gm_msgid}. Expected a tuple but got: {type(raw_imap_msg_data[0])}")
                continue

            try:
                # Pass the raw message data and X-GM-MSGID to the Email object
                email_obj = Email(raw_imap_msg_data[0])
                email_obj.X_GM_MSGID = x_gm_msgid  # Update the X-GM-MSGID from the fetch result
                yield email_obj
            except (TypeError, ValueError) as e:
                logging.error(f"Error processing email with X-GM-MSGID {x_gm_msgid}: {e}")
                logging.debug(f"Raw message data: {raw_imap_msg_data}")

            # Log progress
            if count % 100 == 0 or count == len(x_gm_msgids):
                log_progress(count, total_emails, start_time)

    def fetch_single_email(self, x_gm_msgid: int) -> Email | None:
        """Fetches a single email based on the provided X-GM-MSGID."""
        logging.debug(f"Fetching email with X-GM-MSGID {x_gm_msgid}.")
        retry_count = 3

        for attempt in range(retry_count):
            logging.debug(f"Attempt {attempt + 1}/{retry_count}: Fetching email with X-GM-MSGID {x_gm_msgid}.")
            try:
                # Ensure connection is active
                self.reconnect()

                # Search for the email using X-GM-MSGID
                status, data = self.srv.search(None, f'X-GM-MSGID {x_gm_msgid}')
                if status != "OK" or not data or not data[0]:
                    logging.error(f"Email with X-GM-MSGID {x_gm_msgid} not found.")
                    continue

                # Fetch the email using its UID
                uid = data[0].split()[0]
                result, raw_imap_msg_data = self.srv.fetch(uid, "(RFC822)")

                if result == "OK" and raw_imap_msg_data and raw_imap_msg_data[0]:
                    logging.debug(f"Successfully fetched email with X-GM-MSGID {x_gm_msgid}.")

                    # Validate raw message data
                    if not isinstance(raw_imap_msg_data[0], tuple):
                        logging.error(f"Invalid data format for email with X-GM-MSGID {x_gm_msgid}.")
                        return None

                    # Create and return the Email object
                    email_obj = Email(raw_imap_msg_data[0])
                    email_obj.X_GM_MSGID = x_gm_msgid
                    return email_obj
            except Exception as e:
                logging.error(f"Error during email fetch attempt {attempt + 1}: {e}", exc_info=True)
            time.sleep(2)

        logging.error(f"Failed to fetch email with X-GM-MSGID {x_gm_msgid} after {retry_count} attempts.")
        return None


    def move(self, destination_folder: str, x_gm_msgid: str):
        """
        Moves a single email from one folder to another using X-GM-MSGID.
        """
        logging.debug(f"Moving email with X-GM-MSGID '{x_gm_msgid}' from '{self.mailbox}' to '{destination_folder}'.")
        self.select_box(readonly=False)

        try:
            # Search for the email in the source folder by X-GM-MSGID
            result, data = self.srv.search(None, f'X-GM-MSGID {x_gm_msgid}')
            if result != "OK" or not data or not data[0]:
                logging.debug(f"Email with X-GM-MSGID '{x_gm_msgid}' not found in '{self.mailbox}'.")
                return

            # Extract the email ID
            email_id = data[0].split()[0]
            logging.debug(f"Found email ID '{email_id}' for X-GM-MSGID '{x_gm_msgid}'.")

            # Use the email ID to move the email
            if self.capabilities and b"UIDPLUS" in self.capabilities:
                logging.debug(f"Moving email UID {email_id} to {destination_folder} with UIDPLUS support.")
                result = self.srv.uid('COPY', email_id.decode(), destination_folder)
            else:
                logging.debug(f"Moving email UID {email_id} to {destination_folder} without UIDPLUS support.")
                result = self.srv.copy(email_id.decode(), destination_folder)

            if result[0] == "OK":
                self.srv.store(email_id, '+FLAGS', '\\Deleted')
                self.srv.expunge()
                logging.debug(f"Email with X-GM-MSGID '{x_gm_msgid}' moved successfully.")
            else:
                logging.error(f"Failed to move email with X-GM-MSGID '{x_gm_msgid}'.")
        except Exception as e:
            logging.error(f"Error while moving email with X-GM-MSGID '{x_gm_msgid}': {e}", exc_info=True)
        finally:
            self.srv.close()

    def bulk_move(self, destination_folder: str, x_gm_msgids: list[str]):
        """
        Moves multiple emails from one folder to another in bulk using X-GM-MSGID.

        Parameters:
        - source_folder: The folder to move emails from.
        - destination_folder: The folder to move emails to.
        - x_gm_msgids: A list of email X-GM-MSGIDs as strings.
        """
        try:
            logging.debug(f"Starting bulk move of {len(x_gm_msgids)} emails from '{self.mailbox}' to '{destination_folder}'.")

            # Select source folder
            self.select_box(self.mailbox, readonly=False)

            email_ids = []
            for x_gm_msgid in x_gm_msgids:
                # Search for the email ID in the source folder by X-GM-MSGID
                result, data = self.srv.search(None, f'X-GM-MSGID {x_gm_msgid}')
                if result == "OK" and data and data[0]:
                    email_ids.append(data[0].split()[0])
                    logging.debug(f"Found email ID '{data[0].split()[0]}' for X-GM-MSGID '{x_gm_msgid}'.")
                else:
                    logging.debug(f"Email with X-GM-MSGID '{x_gm_msgid}' not found in '{self.mailbox}'.")

            if not email_ids:
                logging.warning("No emails found for the provided X-GM-MSGIDs. Aborting bulk move.")
                return

            # Ensure email IDs are strings for IMAP operations
            email_ids_str = ",".join(email_ids)

            # Copy emails to destination folder
            result, copy_response = self.srv.uid('COPY', email_ids_str, destination_folder)
            if result != "OK":
                raise IMAP4.error(f"Failed to copy emails to '{destination_folder}': {copy_response}")
            logging.debug(f"Copied {len(email_ids)} emails to '{destination_folder}' successfully.")

            # Mark emails as deleted in source folder
            result, store_response = self.srv.uid("STORE", email_ids_str, "+FLAGS", "(\\Deleted)")
            if result != "OK":
                raise IMAP4.error(f"Failed to mark emails as deleted: {store_response}")
            logging.debug(f"Marked {len(email_ids)} emails as deleted in '{self.mailbox}'.")

            # Expunge to permanently delete emails
            self.srv.expunge()
            logging.info(f"Bulk move completed: {len(email_ids)} emails moved from '{self.mailbox}' to '{destination_folder}'.")

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

    def total_emails(self, folder):
        """
        Returns the total number of emails in the specified folder.
        """
        try:
            # Fetch the status of the folder
            status = self.srv.status(folder, "(MESSAGES)")

            # Extract the numeric value for total messages using regex
            match = re.search(r'MESSAGES (\d+)', status[1][0].decode())
            if match:
                num_emails = int(match.group(1))  # Extracted number from regex
                return num_emails
            else:
                raise ValueError("Couldn't extract the number of messages from the server response.")

        except Exception as e:
            logging.error(f"An error occurred while fetching the total emails in {folder}: {e}", exc_info=True)
            return 0  # Return 0 if there is an error

    def keep_alive(self):
        try:
            self.srv.noop()
            logging.debug("Sent NOOP to keep the IMAP connection alive.")
        except imaplib.IMAP4.abort as e:
            logging.warning(f"IMAP connection aborted: {e}. Reconnecting...")
            self.connect()  # Reconnect if the connection is lost

    def fetch_X_GM_MSGID(self, thread_name: str):
        """
        Fetch all X-GM-MSGIDs from the mailbox and dynamically update the mail queue.

        Args:
            thread_marker (str): The marker to identify the thread in the mail queue.
        """
        try:
            # Perform an IMAP search for all emails
            result, data = self.srv.search(None, "ALL")

            if result != "OK":
                logging.error("Failed to fetch email IDs.")
                return

            ids = data[0].split()
            logging.info(f"Fetching {len(ids)} IDs from {self.mailbox}")

            for index, num in enumerate(ids, start=1):
                # Fetch the email's X-GM-MSGID
                result, msg_data = self.srv.fetch(num, "(X-GM-MSGID)")

                if result == "OK" and msg_data:
                    # Match the X-GM-MSGID value using a regex
                    match = re.search(r'X-GM-MSGID (\d+)', str(msg_data))
                    if match:
                        x_gm_msgid = int(match.group(1))

                        # Update the mail queue with the fetched X-GM-MSGID
                        if self.database.update_mail_queue([x_gm_msgid], thread_name):
                            logging.debug(f"Added X-GM-MSGID {x_gm_msgid} to mail queue with marker '{thread_name}'.")

                # Log progress every 100 emails
                if index % 100 == 0:
                    logging.info(f"{index}/{len(ids)} X-GM-MSGIDs from {self.mailbox} added to que.")
                    self.keep_alive()

            logging.info(f"Finished processing {len(ids)} IDs from {self.mailbox}.")

        except Exception as e:
            logging.error(f"Error fetching X-GM-MSGIDs: {e}", exc_info=True)


class EmailHasher:

    @staticmethod
    def generate_sha256sum(email_content) -> str:
        """
        Generate a SHA-256 hash from the email content.
        """
        if isinstance(email_content, str):
            email_content = email_content.encode('utf-8')
        sha256_hash = hashlib.sha256(email_content).hexdigest()
        return sha256_hash

    