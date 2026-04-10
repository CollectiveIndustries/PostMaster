# post.py
"""
High-level PostOffice interface that delegates to provider implementations
(Gmail, Hotmail, etc.) via the ProviderFactory.
"""

import email
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from providers.factory import ProviderFactory


class PostOffice:
    """
    Controller for email providers.
    Delegates to the correct MailProvider (Gmail, Hotmail, etc.).
    """

    def __init__(self, provider_name: str, config: dict):
        """
        Initialize PostOffice with the given provider.

        Args:
            provider_name (str): Provider key ('gmail', 'hotmail', ...)
            config (dict): Credentials/config for the provider
        """
        self.provider = ProviderFactory.create(provider_name, config=config)

    def connect(self):
        """Authenticate with the provider."""
        self.provider.authenticate()

    def fetch_messages(self, folder: str = "INBOX", limit: int = 50):
        """Fetch messages from the provider."""
        return self.provider.fetch_messages(folder=folder, limit=limit)

    def send_message(self, to: str, subject: str, body: str):
        """Send a message via the provider."""
        return self.provider.send_message(to=to, subject=subject, body=body)

    def close(self):
        """Close the connection to the provider."""
        if hasattr(self.provider, 'close'):
            self.provider.close()

    def logout(self):
        """Logout from the provider."""
        if hasattr(self.provider, 'logout'):
            self.provider.logout()


class Email:
    def __init__(
        self,
        message_id: str,
        subject: str,
        from_addr: str,
        to_addrs: List[str],
        cc_addrs: List[str],
        bcc_addrs: List[str],
        date: str,
        headers: Dict[str, str],
        body_plain: str,
        body_html: Optional[str] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
        labels: Optional[List[str]] = None,
    ):
        self.message_id = message_id
        self.subject = subject
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.cc_addrs = cc_addrs
        self.bcc_addrs = bcc_addrs
        self.date = date
        self.headers = headers
        self.body_plain = body_plain
        self.body_html = body_html
        self.attachments = attachments or []
        self.labels = labels or []  # Gmail tags or NN classification labels

    @classmethod
    def from_mime(cls, raw: bytes):
        """Parse RFC822/MIME into Email object."""
        msg = email.message_from_bytes(raw)

        # Collect headers
        headers = dict(msg.items())

        # Extract parts
        body_plain, body_html = None, None
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = part.get("Content-Disposition", "")
                if ctype == "text/plain" and "attachment" not in disp:
                    body_plain = part.get_payload(decode=True).decode(errors="ignore")
                elif ctype == "text/html" and "attachment" not in disp:
                    body_html = part.get_payload(decode=True).decode(errors="ignore")
                elif "attachment" in disp:
                    attachments.append(
                        {
                            "filename": part.get_filename(),
                            "content_type": ctype,
                            "size": len(part.get_payload(decode=True)),
                        }
                    )
        else:
            body_plain = msg.get_payload(decode=True).decode(errors="ignore")

        return cls(
            message_id=headers.get("Message-ID", ""),
            subject=headers.get("Subject", ""),
            from_addr=headers.get("From", ""),
            to_addrs=[headers.get("To", "")],
            cc_addrs=[headers.get("Cc", "")],
            bcc_addrs=[headers.get("Bcc", "")],
            date=headers.get("Date", ""),
            headers=headers,
            body_plain=body_plain,
            body_html=body_html,
            attachments=attachments,
        )

    def get_text_content(self) -> str:
        """Return cleaned text for ML processing."""
        if self.body_html:
            soup = BeautifulSoup(self.body_html, "html.parser")
            return soup.get_text(separator=" ", strip=True)
        return self.body_plain or ""

    def to_vector_input(self) -> Dict[str, str]:
        """Prepare input for ML (TensorFlow)."""
        return {
            "subject": self.subject,
            "from": self.from_addr,
            "to": " ".join(self.to_addrs),
            "body": self.get_text_content(),
            "labels": " ".join(self.labels),
        }
