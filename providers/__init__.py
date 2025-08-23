# /providers/__init__.py

from .gmail import GmailProvider
from .hotmail import HotmailProvider

# Registry of available providers
PROVIDERS = {"gmail": GmailProvider, "hotmail": HotmailProvider}


def get_provider(name: str, **kwargs):
    """
    Factory function to retrieve the correct provider class.

    Args:
        name (str): Name of the email provider (e.g., 'gmail', 'hotmail').
        **kwargs: Extra args passed into the provider constructor.

    Returns:
        An instance of the requested provider.

    Raises:
        ValueError: If the provider name is not recognized.
    """
    name = name.lower()
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available: {list(PROVIDERS.keys())}")
    return PROVIDERS[name](**kwargs)
