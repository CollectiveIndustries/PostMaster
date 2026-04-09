import argparse

from CollectiveCore.collective_config import CollectiveConfig


class Conf:
    """
    Encapsulates all configuration data for SpamVanquisher.
    Uses CollectiveConfig as the singleton loader.
    """

    def __init__(self, config_path: str = None):
        # Load the singleton config instance
        self._cfg = CollectiveConfig(config_path)

        # Connection settings
        self.EMAIL_ADDRESS = self._cfg.get_value("ConnectionSettings", "email_address")
        self.PASSWORD = self._cfg.get_value("ConnectionSettings", "password")
        self.IMAP_URL = self._cfg.get_value("ConnectionSettings", "url")
        self.IMAP_PORT = self._cfg.get_value("ConnectionSettings", "port", 993)

        # Folder settings
        self.INBOX = self._cfg.get_value("Folders", "inbox")
        self.SPAM_FOLDER = self._cfg.get_value("Folders", "spam_folder")
        self.HAM_FOLDER = self._cfg.get_value("Folders", "ham_folder")
        self.UNSORTED = self._cfg.get_value("Folders", "unsorted")
        self.INFECTED_FOLDER = self._cfg.get_value("Folders", "infected_folder")
        self.SPAM_LEARN = self._cfg.get_value("Folders", "spam_learn")
        self.HAM_LEARN = self._cfg.get_value("Folders", "ham_learn")

        # Daemon settings
        self.TRAINING_DATA_PATH = self._cfg.get_value("DaemonSettings", "data_path")
        self.SCAN_TIME = self._cfg.get_value("DaemonSettings", "scan_time", 300)
        self.BATCH_SIZE = self._cfg.get_value("DaemonSettings", "batch_size", 100)

        # Email parts for training
        self.USE_SUBJECT = self._cfg.get_bool("EmailParts", "use_subject", True)
        self.USE_SENDER = self._cfg.get_bool("EmailParts", "use_sender", True)
        self.USE_RECIPIENT = self._cfg.get_bool("EmailParts", "use_recipient", False)
        self.USE_BODY = self._cfg.get_bool("EmailParts", "use_body", True)

        # MySQL settings
        self.SQL_USER = self._cfg.get_value("MySQL", "user", "SpamVanquisher")
        self.SQL_HOST = self._cfg.get_value("MySQL", "host", "127.0.0.1")
        self.SQL_DATABASE = self._cfg.get_value("MySQL", "database", "SpamVanquisher")
        self.SQL_PASSWORD = self._cfg.get_value("MySQL", "password")
        self.SQL_PORT = self._cfg.get_value("MySQL", "port", 3306)

        # Logger settings
        self.LOG_FILE = self._cfg.get_value("Logging", "log_path", "logs/SpamVanquisher.log")
        self.BACKUP_COUNT = self._cfg.get_value("Logging", "backup_count", 4)
        self.CHECK_INTERVAL = self._cfg.get_value("Logging", "CheckInterval", 300)
        self.MAX_SIZE = self._parse_size(self._cfg.get_value("Logging", "LogSize", "2g"))

    def _parse_size(self, size_str: str) -> int:
        """Convert human-readable size string to bytes (e.g., '2g', '500m', '128k')."""
        size_str = size_str.strip().lower()
        if size_str.endswith("g"):
            return int(float(size_str[:-1]) * 1024**3)
        if size_str.endswith("m"):
            return int(float(size_str[:-1]) * 1024**2)
        if size_str.endswith("k"):
            return int(float(size_str[:-1]) * 1024)
        return int(size_str)

    def db_kwargs(self) -> dict:
        """Return a kwargs dict for mariadb.connect()"""
        return {
            "user": self.SQL_USER,
            "password": self.SQL_PASSWORD,
            "host": self.SQL_HOST,
            "port": self.SQL_PORT,
            "database": self.SQL_DATABASE,
        }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Spam Vanquisher Configuration")
    parser.add_argument("--config", type=str, help="Path to the config YAML file", default=None)
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level",
    )
    return parser.parse_args(argv)


def build_config(argv=None) -> Conf:
    """Factory function to build Conf from CLI or supplied argv list."""
    args = parse_args(argv)
    return Conf(config_path=args.config)

# Module-level singleton instance for easy importing
config = Conf()
