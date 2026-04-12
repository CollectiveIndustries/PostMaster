import imaplib
import logging
import re
import smtplib
import time
from email.mime.text import MIMEText
from typing import Generator, List, Optional

from .base import MailProvider


class GmailProvider(MailProvider):
    """
    Gmail provider using standard IMAP/SMTP with App Passwords.
    No OAuth2 or Google Cloud API required. Operates like a traditional desktop client.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.imap_conn = None
        self.smtp_conn = None
        self.email = config.get("email") or ""

        # Safely handle password which might be None, missing, or contain spaces
        raw_password = config.get("password")
        if isinstance(raw_password, str):
            self.password = raw_password.replace(" ", "")
        else:
            self.password = ""

        self.imap_server = config.get("imap_server", "imap.gmail.com")
        self.imap_port = int(config.get("imap_port", 993))
        self.smtp_server = config.get("smtp_server", "smtp.gmail.com")
        self.smtp_port = int(config.get("smtp_port", 587))
        self._current_folder = None

    def authenticate(self):
        """Authenticate to Gmail using IMAP and SMTP with an App Password."""
        if not self.email or not self.password:
            raise ValueError("Gmail email and password must be provided in configuration.")

        logging.info("Authenticating to Gmail IMAP/SMTP for %s...", self.email)
        try:
            self.imap_conn = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            self.imap_conn.login(self.email, self.password)
            logging.info("IMAP authentication successful.")
        except Exception as e:
            logging.error("IMAP authentication failed: %s", e)
            raise

        try:
            self.smtp_conn = smtplib.SMTP(self.smtp_server, self.smtp_port)
            self.smtp_conn.starttls()
            self.smtp_conn.login(self.email, self.password)
            logging.info("SMTP authentication successful.")
        except Exception as e:
            logging.error("SMTP authentication failed: %s", e)
            raise

    def check_imap_state(self, readonly: bool = False):
        """Check and maintain IMAP connection state."""
        try:
            if self.imap_conn:
                # Ping the server to check connection
                self.imap_conn.noop()
            else:
                self.authenticate()
                if self._current_folder:
                    self.imap_conn.select(self._current_folder, readonly=readonly)
        except Exception as e:
            logging.warning("IMAP connection lost, reconnecting: %s", e)
            self.authenticate()
            if self._current_folder:
                self.imap_conn.select(self._current_folder, readonly=readonly)

    def total_emails(self, folder: str = "INBOX") -> int:
        """Get total number of emails in a folder."""
        if not self.imap_conn:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            status, _ = self.imap_conn.select(folder, readonly=True)
            if status != "OK":
                logging.warning("Failed to select folder: %s", folder)
                return 0

            status, data = self.imap_conn.search(None, "ALL")
            if status != "OK":
                return 0

            msg_ids = data[0].split()
            return len(msg_ids)
        except Exception as e:
            logging.error("Error getting total emails from %s: %s", folder, e)
            return 0

    def fetch_messages(self, folder: str = "INBOX", limit: int = 50):
        """Fetch raw email bytes from the specified folder."""
        if not self.imap_conn:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        status, _ = self.imap_conn.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Failed to select folder: {folder}")

        status, data = self.imap_conn.search(None, "ALL")
        if status != "OK":
            return []

        msg_ids = data[0].split()
        # Fetch the most recent messages up to the limit
        target_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids

        messages = []
        for msg_id in target_ids:
            status, msg_data = self.imap_conn.fetch(msg_id, "(RFC822)")
            if status == "OK" and msg_data[0] is not None:
                messages.append(msg_data[0][1])
        return messages

    def fetch_X_GM_MSGID(self, batch_size: int = 100) -> Generator[List[int], None, None]:
        """
        Fetch X-GM-MSGIDs (Gmail's persistent message IDs) in batches.
        Yields lists of message IDs for batch processing.
        """
        if not self.imap_conn:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        # Select INBOX to search (or could be parameterized)
        status, _ = self.imap_conn.select("INBOX", readonly=True)
        if status != "OK":
            logging.error("Failed to select INBOX for X-GM-MSGID fetch")
            return

        status, data = self.imap_conn.search(None, "ALL")
        if status != "OK":
            return

        msg_ids = data[0].split()
        batch = []

        for msg_id in msg_ids:
            status, msg_data = self.imap_conn.fetch(msg_id, "(X-GM-MSGID)")
            if status == "OK":
                # Parse X-GM-MSGID from response
                msg_str = str(msg_data)
                match = re.search(r'X-GM-MSGID (\d+)', msg_str)
                if match:
                    batch.append(int(match.group(1)))

                    if len(batch) >= batch_size:
                        yield batch
                        batch = []

        if batch:
            yield batch

    def fetch_batch(self, msgids: List[int], batch_size: int = 100) -> Generator[bytes, None, None]:
        """
        Fetch emails by X-GM-MSGID.
        Yields raw email bytes.
        """
        if not self.imap_conn:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        for msgid in msgids:
            try:
                # Search by X-GM-MSGID
                status, data = self.imap_conn.uid('SEARCH', None, f'X-GM-MSGID {msgid}')
                if status == "OK" and data[0]:
                    uid = data[0].split()[0]
                    status, msg_data = self.imap_conn.uid('FETCH', uid, '(RFC822)')
                    if status == "OK" and msg_data[0] is not None:
                        yield msg_data[0][1]
                    else:
                        logging.warning("Failed to fetch email with X-GM-MSGID %s", msgid)
                else:
                    logging.warning("X-GM-MSGID %s not found", msgid)
            except Exception as e:
                logging.error("Error fetching email %s: %s", msgid, e)

    def move(self, uids: List[int], destination_folder: str) -> None:
        """
        Move emails to destination folder using UIDs.
        Note: Gmail uses labels, so this copies to destination and removes from current.
        """
        if not self.imap_conn:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        for uid in uids:
            try:
                # Copy to destination
                self.imap_conn.uid('COPY', uid, destination_folder)
                # Mark for deletion in source
                self.imap_conn.uid('STORE', uid, '+FLAGS', '\\Deleted')
                logging.debug("Moved email UID %s to %s", uid, destination_folder)
            except Exception as e:
                logging.error("Failed to move email UID %s: %s", uid, e)

        # Expunge deleted messages
        try:
            self.imap_conn.expunge()
        except Exception as e:
            logging.warning("Failed to expunge: %s", e)

    def send_message(self, to: str, subject: str, body: str):
        """Send an email message via SMTP."""
        if not self.smtp_conn:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.email
        msg["To"] = to

        self.smtp_conn.sendmail(self.email, [to], msg.as_string())
        logging.info("Email sent to %s", to)

    def close(self):
        """Close IMAP connection."""
        if self.imap_conn:
            try:
                self.imap_conn.close()
                self.imap_conn.logout()
            except Exception:
                pass
            self.imap_conn = None

    def logout(self):
        """Logout from IMAP."""
        self.close()
