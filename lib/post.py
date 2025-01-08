"""
This module provides classes and functions for managing and processing emails using the IMAP protocol.
Classes:
    Email: Represents an email message and provides methods to extract and decode its components.
    PostOffice: Manages the connection to an IMAP server and provides methods to fetch, move, and manage emails.
    EmailHasher: Provides a static method to generate a SHA-256 hash of email content.
Functions:
    Email:
        __init__(raw_data: tuple): Initializes an Email object with raw IMAP fetch data.
        extract_message_parts(raw_msg_data: bytes) -> tuple[str | None, str | None, str | None]: Extracts X-GM-MSGID, message sequence number, and email size from raw message data.
        get_subject(msg): Extracts the subject from the email message.
        get_sender(msg): Extracts the sender from the email message.
        get_recipient(msg): Extracts the recipient from the email message.
        get_payload(msg): Extracts the payload (body) from the email message.
        __repr__(): Returns a string representation of the Email object.
        _decode_email_header(header_value) -> str: Decodes an email header value.
    PostOffice:
        __init__(event: threading.Event, mailbox: str): Initializes a PostOffice object with email settings and mailbox information.
        connect(retry_delay: int = 10): Establishes a connection to the IMAP server with retry logic.
        close(): Closes the mailbox if the server state is 'SELECTED'.
        logout(): Logs out from the IMAP server.
        reconnect(): Ensures the IMAP connection is active and re-selects the folder if necessary.
        select_box(readonly: bool = True): Selects the mailbox for further operations.
        fetch_batch(x_gm_msgids: list[int]) -> Generator[Email, None, None]: Fetches emails based on provided X-GM-MSGID list.
        fetch_single_email(x_gm_msgid: int) -> Email | None: Fetches a single email based on the provided X-GM-MSGID.
        move(destination_folder: str, x_gm_msgid: str): Moves an email to the specified destination folder.
        bulk_move(destination_folder: str, x_gm_msgids: list[str]): Moves multiple emails to the specified destination folder in bulk.
        _check_uidplus_support_() -> bool: Checks if the IMAP server supports the UIDPLUS extension.
        total_emails(folder): Fetches the total number of emails in the specified folder.
        keep_alive(): Sends a NOOP command to the IMAP server to keep the connection alive.
        fetch_X_GM_MSGID(thread_name: str): Fetches all X-GM-MSGIDs from the mailbox and updates the mail queue.
    EmailHasher:
        generate_sha256sum(email_content: bytes) -> str: Generates a SHA-256 hash from the email content.
"""
import logging
import imaplib
import os
import time
import email
import threading
import hashlib
import re
import socket
from typing import Generator
from imaplib import IMAP4
from .database import EmailDatabase
from email.header import decode_header
from .utils import log_progress
from .config import config

class Email:
    """
    A class to represent an email message.
    Attributes:
        subject (str): The subject of the email.
        sender (str): The sender of the email.
        recipient (str): The recipient of the email.
        payload (str): The body of the email.
        classification (None): Placeholder for email classification.
        X_GM_MSGID (str | None): The X-GM-MSGID of the email.
        msg_sequence (str | None): The message sequence number.
        email_size (str | None): The size of the email.
        hash (str): The SHA-256 hash of the email content.
    Methods:
        __init__(raw_data: tuple):
            Initializes the Email object with raw data from an IMAP fetch command.
        extract_message_parts(raw_msg_data: bytes) -> tuple[str | None, str | None, str | None]:
        _get_subject(msg):
            Extracts the subject from the email message.
        _get_sender(msg):
            Extracts the sender from the email message.
        _get_recipient(msg):
            Extracts the recipient from the email message.
        _get_payload(msg):
            Extracts the email payload (body of the email).
        __repr__():
            Returns a string representation of the Email object.
        _decode_email_header(header_value) -> str:
            Decodes an email header to a readable string.
    """
    def __init__(self, raw_data: tuple):
        # msg_data is the result of an IMAP fetch command
        if not raw_data or not isinstance(raw_data, tuple):
            raise ValueError("Invalid raw_data format. Expected a tuple.")
        raw_email = raw_data[1]
        msg = email.message_from_bytes(raw_email)

        self.subject = self._get_subject(msg)
        self.sender = self._get_sender(msg)
        self.recipient = self._get_recipient(msg)
        self.payload = self._get_payload(msg)
        self.classification = None
        self.X_GM_MSGID, self.msg_sequence, self.email_size = self.extract_message_parts(raw_data[0])
        self.hash = EmailHasher.generate_sha256sum(raw_data[1])

    def extract_message_parts(self, raw_msg_data: bytes) -> tuple[str | None, str | None, str | None]:
        """
        Extracts X-GM-MSGID, message sequence number, and email size from raw message data using regular expressions.
        Args:
            raw_msg_data (bytes): The raw message data from which to extract the parts.
        Returns:
            tuple: A tuple containing the X-GM-MSGID (str), message sequence number (str), and email size (str).
               If any part is not found, its value in the tuple will be None.
        Raises:
            None: This method handles exceptions internally and logs errors.
        """
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

    def _get_subject(self, msg):
        # Extract subject from the message
        return self._decode_email_header(msg.get("Subject"))

    def _get_sender(self, msg):
        return self._decode_email_header(msg.get("From"))

    def _get_recipient(self, msg):
        return self._decode_email_header(msg.get("To"))

    def _get_payload(self, msg):
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
        return f"Email(subject={self.subject}, sender={self.sender}, recipient={self.recipient}, X_GM_MSGID={self.X_GM_MSGID})"

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
        self.srv = None
        self.capabilities = None
        self.email = config.EMAIL_ADDRESS
        self.password = config.PASSWORD
        self.url = config.IMAP_URL
        self.port = int(config.IMAP_PORT)
        self._StopEvent = event
        self._check_uidplus_support_()
        self.mailbox = mailbox
        self.database = EmailDatabase()

    def connect(self, retry_delay: int = 10):
        """
        Establish a connection to the IMAP server in an endless loop unless stop_event is set.

        Parameters:
        - retry_delay (int): Delay in seconds between retries.
        """
        while not self._StopEvent.is_set():
            try:
                logging.debug(f"Attempting to connect to IMAP server {self.url}:{self.port}.")
                # Check network connectivity
                with socket.create_connection((self.url, self.port), timeout=10):
                    logging.debug(f"Network connectivity to {self.url}:{self.port} verified.")

                # Attempt IMAP connection
                self.srv = imaplib.IMAP4_SSL(self.url, self.port)
                self.srv.login(self.email, self.password)
                logging.info(f"Connected to IMAP server {self.url} on port {self.port}.")
                return  # Exit the loop upon successful connection

            except (socket.error, imaplib.IMAP4.error) as e:
                logging.warning(f"Connection attempt failed: {e}")
                self.srv = None

            # Wait before retrying
            logging.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

        # If we exit due to stop_event being set
        logging.info("Stop event set. Exiting connection attempts.")

    def close(self):
        """
        Closes the mailbox if the server state is 'SELECTED'.

        This method attempts to close the mailbox by checking the server's state.
        If the state is 'SELECTED', it closes the server connection and logs a success message.
        If the state is not 'SELECTED', it logs a warning message indicating the current state.
        In case of any exceptions during the process, it logs an error message with the exception details.
        """
        try:
            # Check if the server state is 'SELECTED'
            if self.srv.state == 'SELECTED':
                self.srv.close()
                logging.info("Mailbox closed successfully.")
            else:
                logging.warning(f"Cannot close mailbox. Current state: '{self.srv.state}'. Expected: 'SELECTED'.")
        except Exception as e:
            logging.error(f"Error while closing the mailbox: {e}", exc_info=True)

    def logout(self):
        """
        Logs out from the IMAP server and records the action in the log.

        This method calls the `logout` function of the `srv` attribute to 
        terminate the session with the IMAP server. It also logs an 
        informational message indicating that the logout was successful.
        """
        if self.srv is None:
            logging.warning("No active IMAP connection to log out from.")
            return
        else:
            try:
                self.srv.logout()
                logging.info("Logged out from IMAP server.")
            except Exception as e:
                logging.error(f"Error during logout: {e}", exc_info=True)
                return

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
        """
        Selects the mailbox for further operations.

        Parameters:
        readonly (bool): If True, the mailbox is opened in read-only mode. Defaults to True.

        Raises:
        IMAP4.error: If there is an error selecting the mailbox.

        Logs:
        Debug: Successfully connected to the mailbox.
        Error: IMAP connection error selecting the mailbox.
        """
        try:
            self.srv.select(self.mailbox, readonly) # DO NOT flag mail as read.
            logging.debug(f"Successfully connected to mailbox '{self.mailbox}'.")
        except IMAP4.error as e:
            logging.error(f"IMAP connection error selecting mailbox: {e}")

    def fetch_batch(self, x_gm_msgids: list[int]) -> Generator[Email, None, None]:
        """
        Fetches emails based on provided x_gm_msgid list.

        Args:
            x_gm_msgids (list[int]): List of X-GM-MSGID values to fetch emails for.

        Yields:
            Email: An Email object containing the fetched email data.

        Logs:
            - Information about the total number of emails to fetch.
            - Progress of fetching emails.
            - Errors encountered during fetching and processing emails.
            - Debug information for each fetch attempt.

        Notes:
            - Retries fetching each email up to 3 times in case of failure.
            - Stops fetching if a stop signal is received.
            - Logs progress every 100 emails or at the end of the batch.
        """
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

    def search_with_retry(self, x_gm_msgid: int) -> str | None:
        """
        Searches for an email with the given X-GM-MSGID.

        Args:
            x_gm_msgid (int): The X-GM-MSGID of the email to search for.

        Returns:
            str | None: The UID of the email if found, otherwise None.

        This method attempts to search for an email. If a failure occurs,
        it reconnects, reselects the mailbox, and retries the search.
        """
        self.check_imap_state()
        count = 0
        while True:
            try:
                # Perform the search
                status, data = self.srv.search(None, f'X-GM-MSGID {x_gm_msgid}')
                if status == "OK" and data:
                    if data[0] == b'':
                        logging.debug(f"Email with X-GM-MSGID {x_gm_msgid} not found.")
                        return None
                    logging.debug(f"Email with X-GM-MSGID {x_gm_msgid} found.")
                    return data
            except Exception as e:
                logging.warning(f"Search failed for X-GM-MSGID {x_gm_msgid}: {e}. Attempt {count + 1}")

            logging.debug(f"Retrying search for X-GM-MSGID {x_gm_msgid}.")
            count += 1

    def fetch_single_email(self, x_gm_msgid: int) -> Email | None:
        """
        Fetches a single email based on the provided X-GM-MSGID.

        Args:
            x_gm_msgid (int): The X-GM-MSGID of the email to fetch.

        Returns:
            Email | None: The fetched Email object if successful, otherwise None.
        """
        logging.debug(f"Fetching email with X-GM-MSGID {x_gm_msgid}.")
        retry_count = 3

        for attempt in range(retry_count):
            logging.debug(f"Attempt {attempt + 1}/{retry_count}: Fetching email with X-GM-MSGID {x_gm_msgid}.")
            try:
                # Ensure connection is active
                self.check_imap_state

                # Use the extracted search_with_retry method
                uid = self.search_with_retry(x_gm_msgid)
                if not uid:
                    continue  # Skip to the next retry if the email is not found

                # Fetch the email using its UID
                result, raw_imap_msg_data = self.srv.fetch(uid[0].split()[0], "(RFC822)")
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

        logging.debug(f"Failed to fetch email with X-GM-MSGID {x_gm_msgid} after {retry_count} attempts.")
        self.database.mark_email_as_failed(x_gm_msgid)
        return None

    def move(self, destination_folder: str, x_gm_msgid: str):
        """
        Args:
            destination_folder (str): The name of the destination folder where the email should be moved.
            x_gm_msgid (str): The X-GM-MSGID of the email to be moved.
        Returns:
            None
        Logs:
            - Debug information about the process of moving the email.
            - Error information if the email could not be moved.
        Raises:
            Exception: If an error occurs during the process of moving the email.
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
        """
        Checks if the IMAP server supports the UIDPLUS extension (RFC 4315).

        This method connects to the IMAP server, queries its capabilities, and checks if UIDPLUS is supported.
        It logs the server capabilities and whether UIDPLUS is supported or not.

        Returns:
            bool: True if the server supports UIDPLUS, False otherwise.

        Raises:
            imaplib.IMAP4.error: If there is an IMAP4 protocol error.
            Exception: If there is an unexpected error.
        """
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

            return uidplus_supported

        except imaplib.IMAP4.error as e:
            logging.critical(f"IMAP4 error: {e}")
        except Exception as e:
            logging.critical(f"Unexpected error: {e}")
        return False

    def total_emails(self, folder):
        """
        Fetches the total number of emails in the specified folder.

        Args:
            folder (str): The name of the folder to check for emails.

        Returns:
            int: The total number of emails in the folder. Returns 0 if an error occurs.

        Raises:
            ValueError: If the number of messages cannot be extracted from the server response.
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
            logging.error(f"An error occurred while fetching the total emails in '{folder}': {e}", exc_info=True)
            return 0  # Return 0 if there is an error

    def keep_alive(self):
        """
        Sends a NOOP command to the IMAP server to keep the connection alive.
        
        If the connection is aborted, logs a warning and attempts to reconnect.
        
        Raises:
            imaplib.IMAP4.abort: If the IMAP connection is aborted.
        """
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
        # TODO refactor into a generator that grabs X-GM-MSGIDs in batches
        try:
            # Perform an IMAP search for all emails
            self.check_imap_state()
            result, data = self.srv.search(None, "ALL")

            if result != "OK":
                logging.error("Failed to fetch email IDs.")
                return

            ids = data[0].split()
            if len(ids) == 0:
                logging.debug(f"No emails found in {self.mailbox}.")
                return

            logging.info(f"Fetching {len(ids)} IDs from '{self.mailbox}'")
            start_time = time.time()

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
                    log_progress(index, len(ids), start_time)
                    self.keep_alive()

                if self._StopEvent.is_set():
                    logging.info("Stop signal received. shutting down PostOffice.")
                    break

            if len(ids) > 0:
                logging.info(f"Finished processing {len(ids)} IDs from {self.mailbox}.")

        except Exception as e:
            logging.error(f"Error fetching X-GM-MSGIDs: {e}", exc_info=True)

    def check_imap_state(self, readonly: bool = True):
        """
        Ensures that the IMAP connection is in the correct state for operations.
        Handles transitions from NONAUTH to AUTH to SELECTED as needed, and re-connects if in LOGOUT state.

        Args:
            readonly (bool): If True, opens the mailbox in readonly mode.

        Raises:
            Exception: If the connection cannot be brought to the required state.
        """
        try:
            # If the connection is in LOGOUT state, reconnect and authenticate
            if self.srv.state == "LOGOUT":
                logging.debug("IMAP connection in LOGOUT state. Reconnecting...")
                self.connect()

            # If the connection is in NONAUTH state, reconnect and authenticate
            elif self.srv.state == "NONAUTH":
                logging.debug("IMAP connection in NONAUTH state. Reconnecting...")
                self.connect()

            # If the connection is in AUTH state, select the mailbox if needed
            elif self.srv.state == "AUTH":
                if self.mailbox:
                    logging.debug(f"IMAP connection in AUTH state. Selecting mailbox '{self.mailbox}'...")
                    status, _ = self.srv.select(self.mailbox, readonly=readonly)  # Select the mailbox
                    if status != "OK":
                        raise Exception(f"Failed to select mailbox '{self.mailbox}'.")
                else:
                    logging.debug("IMAP connection in AUTH state. No mailbox specified to select.")

            # If the connection is already in SELECTED state, ensure the correct mailbox is selected
            elif self.srv.state == "SELECTED" and self.mailbox:
                logging.debug(f"Ensuring the correct mailbox is selected: {self.mailbox}")
                status, _ = self.srv.select(self.mailbox)  # Re-select the desired mailbox directly
                if status != "OK":
                    raise Exception(f"Failed to ensure mailbox '{self.mailbox}' is selected.")

            # If none of the above states, raise an error as the connection is in an unexpected state
            else:
                raise Exception(f"Unexpected IMAP state: {self.srv.state}")

        except Exception as e:
            logging.error(f"Error ensuring IMAP state: {e}", exc_info=True)
            raise

    def save(self, path: str):
        """
        Save all emails from the specified mailbox to the local file system as .eml files.

        Args:
            path (str): The path where the emails will be saved.
        """
        try:
            # Ensure the save path exists
            if not os.path.exists(path):
                os.makedirs(path)

            self.connect()
            self.select_box(readonly=True)
            if status != "OK":
                raise Exception(f"Failed to select mailbox: {self.mailbox}")

            # Fetch all email IDs in the mailbox
            logging.info(f"Fetching email IDs from mailbox: {self.mailbox}")
            status, email_ids = self.srv.search(None, "ALL")
            if status != "OK":
                raise Exception("Failed to fetch email IDs.")

            email_ids = email_ids[0].split()
            logging.info(f"Found {len(email_ids)} emails in mailbox '{self.mailbox}'.")

            # Fetch and save each email
            for idx, email_id in enumerate(email_ids, start=1):
                if self._StopEvent.is_set():
                    logging.info("Stop signal received. Halting the save operation.")
                    break

                # Fetch the email by ID
                status, data = self.srv.fetch(email_id, "(RFC822)")
                if status != "OK":
                    logging.warning(f"Failed to fetch email ID {email_id}. Skipping.")
                    continue

                # Parse the email content
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Generate a filename based on the subject or email ID
                subject = msg.get("Subject", "No_Subject").replace("/", "_").replace("\\", "_")
                filename = f"{idx}_{subject}.eml"

                # Save the email locally
                email_path = os.path.join(path, filename)
                with open(email_path, "wb") as f:
                    f.write(raw_email)
                logging.info(f"Saved email {idx}: {email_path}")

                # Optional: You could also store metadata like the email ID in a database here if needed

            logging.info(f"Finished saving {len(email_ids)} emails from '{self.mailbox}' to {path}.")

        except Exception as e:
            logging.error(f"An error occurred during the email save operation: {e}", exc_info=True)

        finally:
            self.close()
            self.logout()

class EmailHasher:

    @staticmethod
    def generate_sha256sum(email_content: bytes) -> str:
        """
        Generate a SHA-256 hash from the email content.

        Args:
            email_content (bytes): The content of the email to hash.

        Returns:
            str: The SHA-256 hash of the email content.

        Raises:
            ValueError: If the email content is not of type bytes.
        """
        if not isinstance(email_content, bytes):
            raise ValueError("email_content must be of type bytes.")
        
        sha256_hash = hashlib.sha256(email_content).hexdigest()
        return sha256_hash

def extract_email_data(email: Email):
    """
    Extracts data from the email based on configuration settings.
    """
    data = []
    if config.USE_SUBJECT:
        data.append(email.subject)
    if config.USE_SENDER:
        data.append(email.sender)
    if config.USE_RECIPIENT:
        data.append(email.recipient)
    if config.USE_BODY:
        data.append(email.payload)
    return " ".join(data)
