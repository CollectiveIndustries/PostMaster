# providers/gmail.py
import base64
from email.mime.text import MIMEText

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .base import MailProvider


class GmailProvider(MailProvider):
    SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

    def __init__(self, config: dict):
        super().__init__(config)
        self.service = None

    def authenticate(self):
        """Authenticate to Gmail using OAuth2 flow."""
        flow = InstalledAppFlow.from_client_secrets_file(self.config["credentials_file"], self.SCOPES)
        creds = flow.run_local_server(port=0)
        self.service = build("gmail", "v1", credentials=creds)

    def fetch_messages(self, folder: str = "INBOX", limit: int = 50):
        logging.debug(f"Fetching {limit} messages from {folder}")
        try:
            results = self.service.users().messages().list(userId="me", labelIds=[folder], maxResults=limit).execute()
            messages = results.get("messages", [])
            logging.debug(f"Found {len(messages)} messages in {folder}")
            return messages
        except Exception as e:
            logging.error(f"Gmail API error: {str(e)}")
            raise

    def send_message(self, to: str, subject: str, body: str):
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = self.service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return sent
