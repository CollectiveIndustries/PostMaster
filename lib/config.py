"""Configuration wrapper that uses the lazy ConfigManager."""

import logging
from typing import Optional

from .config_manager import config_manager


class Conf:
    """
    Encapsulates all configuration data for SpamVanquisher.
    Uses ConfigManager as the lazy singleton loader.
    """

    def __init__(self, config_path: Optional[str] = None):
        # Store path for later initialization (but don't load yet)
        self._pending_path = config_path
        self._initialized = False
        self._show_config = False

    def _ensure_initialized(self):
        """Load config if not already loaded."""
        if not self._initialized:
            config_manager.initialize(self._pending_path)
            self._load_attributes()
            self._initialized = True

    def _load_attributes(self):
        """Load all configuration attributes from the manager."""
        # Connection settings (from ConnectionSettings section)
        conn_settings = config_manager.get_section('ConnectionSettings')
        self.EMAIL_ADDRESS = conn_settings.get('email_address', '') if conn_settings else ''
        self.PASSWORD = conn_settings.get('password', '').replace(' ', '') if conn_settings else ''
        self.IMAP_URL = conn_settings.get('url', 'imap.gmail.com') if conn_settings else 'imap.gmail.com'
        self.IMAP_PORT = conn_settings.get('port', 993) if conn_settings else 993

        # Folder settings
        folders = config_manager.get_section('Folders')
        self.INBOX = folders.get('inbox', 'INBOX') if folders else 'INBOX'
        self.SPAM_FOLDER = folders.get('spam_folder', 'SPAM') if folders else 'SPAM'
        self.HAM_FOLDER = folders.get('ham_folder', 'HAM') if folders else 'HAM'
        self.UNSORTED = folders.get('unsorted', 'UNSORTED') if folders else 'UNSORTED'
        self.INFECTED_FOLDER = folders.get('infected_folder', 'INFECTED') if folders else 'INFECTED'
        self.SPAM_LEARN = folders.get('spam_learn', 'SPAM_LEARN') if folders else 'SPAM_LEARN'
        self.HAM_LEARN = folders.get('ham_learn', 'HAM_LEARN') if folders else 'HAM_LEARN'

        # Daemon settings - FORCE READ FROM CONFIG MANAGER
        daemon = config_manager.get_section('DaemonSettings')
        if daemon and 'data_path' in daemon:
            self.TRAINING_DATA_PATH = daemon.get('data_path')
            logging.info(f"Loaded TRAINING_DATA_PATH from config: {self.TRAINING_DATA_PATH}")
        else:
            # Fallback to config value or default
            self.TRAINING_DATA_PATH = '/opt/spamvanquisher/data'
            logging.warning(f"DaemonSettings.data_path not found, using: {self.TRAINING_DATA_PATH}")

        self.SCAN_TIME = daemon.get('scan_time', 300) if daemon else 300
        self.BATCH_SIZE = daemon.get('batch_size', 100) if daemon else 100

        # Email parts for training
        email_parts = config_manager.get_section('EmailParts')
        self.USE_SUBJECT = email_parts.get('use_subject', True) if email_parts else True
        self.USE_SENDER = email_parts.get('use_sender', True) if email_parts else True
        self.USE_RECIPIENT = email_parts.get('use_recipient', False) if email_parts else False
        self.USE_BODY = email_parts.get('use_body', True) if email_parts else True

        # MySQL settings (from MySQL section)
        mysql_settings = config_manager.get_section('MySQL')
        self.SQL_USER = mysql_settings.get('user', 'SpamVanquisher') if mysql_settings else 'SpamVanquisher'
        self.SQL_HOST = mysql_settings.get('host', '127.0.0.1') if mysql_settings else '127.0.0.1'
        self.SQL_DATABASE = mysql_settings.get('database', 'SpamVanquisher') if mysql_settings else 'SpamVanquisher'
        self.SQL_PASSWORD = mysql_settings.get('password', '') if mysql_settings else ''
        self.SQL_PORT = mysql_settings.get('port', 3306) if mysql_settings else 3306

        # Also support 'database' section as fallback (for compatibility)
        db_settings = config_manager.get_section('database')
        if db_settings:
            self.SQL_USER = db_settings.get('user', self.SQL_USER)
            self.SQL_PASSWORD = db_settings.get('password', self.SQL_PASSWORD)
            self.SQL_HOST = db_settings.get('host', self.SQL_HOST)
            self.SQL_DATABASE = db_settings.get('database', self.SQL_DATABASE)
            self.SQL_PORT = db_settings.get('port', self.SQL_PORT)

        # Logger settings
        logging_cfg = config_manager.get_section('Logging')
        self.LOG_FILE = (
            logging_cfg.get('log_path', 'logs/SpamVanquisher.log') if logging_cfg else 'logs/SpamVanquisher.log'
        )
        self.BACKUP_COUNT = logging_cfg.get('backup_count', 4) if logging_cfg else 4
        self.CHECK_INTERVAL = logging_cfg.get('CheckInterval', 300) if logging_cfg else 300
        self.MAX_SIZE = self._parse_size(logging_cfg.get('LogSize', '2g')) if logging_cfg else 2 * 1024**3

        # Print config if enabled
        if self._show_config:
            self._print_config()

    def _print_config(self):
        """Print configuration with passwords masked"""
        logging.info("🔧 Loaded Configuration:")
        logging.info(f"  EMAIL_ADDRESS: {self.EMAIL_ADDRESS}")
        logging.info(f"  PASSWORD: {'*' * len(self.PASSWORD) if self.PASSWORD else 'NOT SET'}")
        logging.info(f"  TRAINING_DATA_PATH: {self.TRAINING_DATA_PATH}")
        logging.info(f"  SCAN_TIME: {self.SCAN_TIME}")
        logging.info(f"  BATCH_SIZE: {self.BATCH_SIZE}")

    def _parse_size(self, size_str: str) -> int:
        """Convert human-readable size string to bytes."""
        if not size_str:
            return 2 * 1024**3
        size_str = str(size_str).strip().lower()
        if size_str.endswith('g'):
            return int(float(size_str[:-1]) * 1024**3)
        if size_str.endswith('m'):
            return int(float(size_str[:-1]) * 1024**2)
        if size_str.endswith('k'):
            return int(float(size_str[:-1]) * 1024)
        return int(size_str)

    def db_kwargs(self) -> dict:
        """Return a kwargs dict for mariadb.connect()"""
        self._ensure_initialized()
        return {
            "user": self.SQL_USER,
            "password": self.SQL_PASSWORD,
            "host": self.SQL_HOST,
            "port": self.SQL_PORT,
            "database": self.SQL_DATABASE,
        }

    def validate(self) -> None:
        """Validate critical configuration values before application startup."""
        self._ensure_initialized()
        errors = []
        if not self.IMAP_URL or not str(self.IMAP_URL).strip():
            errors.append("IMAP URL is empty or missing in ConnectionSettings.url")
        if not self.EMAIL_ADDRESS or not str(self.EMAIL_ADDRESS).strip():
            errors.append("Email address is empty or missing in ConnectionSettings.email_address")
        if not self.PASSWORD or not str(self.PASSWORD).strip():
            errors.append("Password is empty or missing in ConnectionSettings.password")

        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f" - {e}" for e in errors))

    def __getattr__(self, name):
        """Fallback for direct attribute access."""
        self._ensure_initialized()
        if name in self.__dict__:
            return self.__dict__[name]
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")


# Create the singleton instance
config = Conf()


def build_config(config_path: Optional[str] = None) -> Conf:
    """Factory function to build Conf from config path."""
    return Conf(config_path=config_path)
