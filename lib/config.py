import configparser
import logging
import argparse

class conf:
    def __init__(self, config_file="config.ini"):
        CONFIG = configparser.ConfigParser()
        CONFIG.read(config_file)

        # Connection settings
        self.EMAIL_ADDRESS = CONFIG.get('ConnectionSettings', 'email_address')
        self.PASSWORD = CONFIG.get('ConnectionSettings', 'password')
        self.IMAP_URL = CONFIG.get('ConnectionSettings', 'url')
        self.IMAP_PORT = int(CONFIG.get('ConnectionSettings', 'port'))

        # Folder settings
        self.INBOX = CONFIG.get('Folders', 'inbox')
        self.SPAM_FOLDER = CONFIG.get('Folders', 'spam_folder')
        self.HAM_FOLDER = CONFIG.get('Folders', 'ham_folder')
        self.INFECTED_FOLDER = CONFIG.get('Folders', 'infected_folder')
        self.SPAM_LEARN = CONFIG.get('Folders', 'spam_learn')
        self.HAM_LEARN = CONFIG.get('Folders', 'ham_learn')

        # Daemon Settings
        self.TRAINING_DATA_PATH = CONFIG.get('DaemonSettings', 'data_path')
        self.FAILED_UID_FILE = f"{CONFIG.get('DaemonSettings', 'data_path')}/failed_uids.json" # placeholder config value
        self.SCAN_TIME = int(CONFIG.get('DaemonSettings', 'scan_time'))

        # Log Settings
        self.LOG_FILE = CONFIG.get('Logs', 'log_file')
        self.LOG_LEVEL = CONFIG.get('Logs', 'log_level', fallback="INFO").upper()
        self.MAX_SIZE = int(CONFIG.get('Logs', 'max_size_mb', fallback=10)) * 1024 * 1024
        self.BACKUP_COUNT = int(CONFIG.get('Logs', 'backup_count', fallback=5))
        self.CHECK_INTERVAL = int(CONFIG.get('Logs', 'check_interval', fallback=60))
        
        # TODO Network maping method to config file (kinda lost the idea on what this was about)
        # Load Email Parts Settings
        self.USE_SUBJECT = CONFIG.getboolean('EmailParts', 'use_subject', fallback=True)
        self.USE_SENDER = CONFIG.getboolean('EmailParts', 'use_sender', fallback=True)
        self.USE_RECIPIENT = CONFIG.getboolean('EmailParts', 'use_recipient', fallback=False)
        self.USE_BODY = CONFIG.getboolean('EmailParts', 'use_body', fallback=True)


        # Clear any existing handlers and setup logging explicitly
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        file_handler = logging.FileHandler(self.LOG_FILE)
        file_handler.setLevel(getattr(logging, self.LOG_LEVEL, logging.INFO))
        formatter = logging.Formatter('%(asctime)s %(threadName)s %(name)s[%(process)d]: %(levelname)s: %(message)s')
        file_handler.setFormatter(formatter)

        logging.root.addHandler(file_handler)
        logging.root.setLevel(getattr(logging, self.LOG_LEVEL, logging.INFO))

        logging.info(f"Configuration settings loaded from {config_file}.")

# Argument parsing to allow for custom config file path
def parse_args():
    parser = argparse.ArgumentParser(description="Spam Vanquisher Configuration")
    parser.add_argument('--config', type=str, help="Path to the config.ini file", default="config.ini")
    return parser.parse_args()

# Parse arguments
args = parse_args()

# Pass the config file path to the conf class
config = conf(config_file=args.config)