# /providers/factory.py

from . import PROVIDERS, get_provider


class ProviderFactory:
    """
    Factory class for creating email provider instances.
    """

    @staticmethod
    def available_providers():
        """
        List all available providers.
        """
        return list(PROVIDERS.keys())

    @staticmethod
    def create(name: str, **kwargs):
        """
        Create an instance of the requested provider.

        Args:
            name (str): Provider name (e.g., 'gmail', 'hotmail').
            **kwargs: Extra args passed to the provider class.

        Returns:
            An instance of the provider class.
        """
        return get_provider(name, **kwargs)
