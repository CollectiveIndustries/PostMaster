# providers/base.py
from abc import ABC, abstractmethod


class MailProvider(ABC):
    """
    Abstract base class for mail providers.
    Defines the common interface for authentication and fetching mail.
    """

    def __init__(self, config: dict):
        """
        config: dict containing provider-specific credentials/settings
        """
        self.config = config

    @abstractmethod
    def authenticate(self):
        """Authenticate with the provider using given credentials."""
        raise NotImplementedError

    @abstractmethod
    def fetch_messages(self, folder: str = "INBOX", limit: int = 50):
        """Fetch messages from the given folder."""
        raise NotImplementedError

    @abstractmethod
    def send_message(self, to: str, subject: str, body: str):
        """Send an email message."""
        raise NotImplementedError
