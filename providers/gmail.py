import imaplib
import logging
import smtplib
from email.mime.text import MIMEText

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
