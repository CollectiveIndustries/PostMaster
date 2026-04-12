# providers/base.py
from abc import ABC, abstractmethod
from typing import List, Generator, Optional


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

    # ========== Additional methods required by PostMaster ==========

    def total_emails(self, folder: str = "INBOX") -> int:
        """
        Get total number of emails in a folder.
        Default implementation returns 0 - override in provider.
        """
        return 0

    def fetch_X_GM_MSGID(self, batch_size: int = 100) -> Generator[List[int], None, None]:
        """
        Fetch X-GM-MSGIDs (Gmail's persistent message IDs) in batches.
        Yields lists of message IDs for batch processing.
        Default implementation yields empty list - override in provider.
        """
        yield []

    def fetch_batch(self, msgids: List[int], batch_size: int = 100) -> Generator[bytes, None, None]:
        """
        Fetch emails by X-GM-MSGID.
        Yields raw email bytes.
        Default implementation yields nothing - override in provider.
        """
        return
        yield  # This makes it a generator

    def move(self, uids: List[int], destination_folder: str) -> None:
        """
        Move emails to destination folder.
        Default implementation does nothing - override in provider.
        """
        pass

    def check_imap_state(self, readonly: bool = False) -> None:
        """
        Check and maintain IMAP connection state.
        Default implementation does nothing - override in provider.
        """
        pass

    def close(self) -> None:
        """Close the connection to the provider."""
        pass

    def logout(self) -> None:
        """Logout from the provider."""
        pass