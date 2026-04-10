#!/usr/bin/env python3
import os

import yaml

# Directory where default config will be saved
CONFIG_DIR = "config.d"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")

# Default configuration template
DEFAULT_CONFIG = {
    "ConnectionSettings": {
        "email_address": "user@example.com",
        "password": "change_me",
        "url": "imap.example.com",
        "port": 993,
    },
    "Folders": {
        "inbox": "INBOX",
        "spam_folder": "SPAM",
        "ham_folder": "HAM",
        "unsorted": "UNSORTED",
        "infected_folder": "INFECTED",
        "spam_learn": "SPAM_LEARN",
        "ham_learn": "HAM_LEARN",
    },
    "DaemonSettings": {"data_path": "/var/lib/spamvanquisher/data", "scan_time": 300, "batch_size": 100},
    "EmailParts": {"use_subject": True, "use_sender": True, "use_recipient": False, "use_body": True},
    "MySQL": {
        "user": "SpamVanquisher",
        "host": "127.0.0.1",
        "database": "SpamVanquisher",
        "password": "change_me",
        "port": 3306,
    },
    "Logging": {"log_path": "logs/SpamVanquisher.log", "backup_count": 4, "CheckInterval": 300, "LogSize": "2g"},
}


def write_default_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        print(f"{CONFIG_FILE} already exists. Skipping write.")
        return
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_CONFIG, f, sort_keys=False)
    print(f"Default configuration written to {CONFIG_FILE}")


if __name__ == "__main__":
    write_default_config()
