# providers/hotmail.py
import msal
import requests

from .base import MailProvider


class HotmailProvider(MailProvider):
    SCOPES = ["Mail.Read", "Mail.Send"]

    def __init__(self, config: dict):
        super().__init__(config)
        self.access_token = None

    def authenticate(self):
        """Authenticate to Outlook/Hotmail using MSAL + OAuth2."""
        app = msal.PublicClientApplication(self.config["client_id"], authority=self.config["authority"])
        result = app.acquire_token_interactive(self.SCOPES)
        if "access_token" in result:
            self.access_token = result["access_token"]
        else:
            raise RuntimeError("Authentication failed")

    def fetch_messages(self, folder: str = "inbox", limit: int = 50):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        endpoint = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages" f"?$top={limit}"
        response = requests.get(endpoint, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json().get("value", [])

    def send_message(self, to: str, subject: str, body: str):
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": "true",
        }
        response = requests.post(
            "https://graph.microsoft.com/v1.0/me/sendMail", headers=headers, json=payload, timeout=30
        )
        response.raise_for_status()
        return {"status": "sent"}
