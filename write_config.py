#!/usr/bin/env python3
"""
Write default configuration file for PostMaster
Usage: python write_config.py [--config-dir DIR] [--force]
"""

import argparse
import os
import sys

import yaml

# Default configuration template - UPDATED with correct paths
DEFAULT_CONFIG = {
    "ConnectionSettings": {
        "email_address": "user@example.com",
        "password": "change_me",
        "url": "imap.gmail.com",
        "port": 993,
    },
    "Folders": {
        "inbox": "INBOX",
        "spam_folder": "INBOX/Spam",
        "ham_folder": "INBOX/Ham",
        "unsorted": "UNSORTED",
        "infected_folder": "INFECTED",
        "spam_learn": "INBOX/spam_learn",
        "ham_learn": "INBOX/ham_learn",
    },
    "DaemonSettings": {
        "data_path": "/opt/spamvanquisher/data",  # FIXED: Changed from /var/lib
        "scan_time": 300,
        "batch_size": 10,  # Changed from 100 to 10 for better batch processing
    },
    "EmailParts": {"use_subject": True, "use_sender": True, "use_recipient": False, "use_body": True},
    "MySQL": {
        "user": "postmaster_user",  # FIXED: Changed from SpamVanquisher
        "host": "localhost",
        "database": "postmaster_db",  # FIXED: Changed from SpamVanquisher
        "password": "change_me",
        "port": 3306,
    },
    "Logging": {"log_path": "logs/SpamVanquisher.log", "backup_count": 4, "CheckInterval": 300, "LogSize": "2g"},
}


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Write default configuration for PostMaster',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                              # Write to default location (config.d/config.yaml)
    %(prog)s --config-dir /opt/config.d   # Write to /opt/config.d/config.yaml
    %(prog)s --force                      # Overwrite existing config
        """,
    )
    parser.add_argument(
        '--config-dir', '-d', type=str, default='config.d', help='Configuration directory (default: config.d)'
    )
    parser.add_argument('--force', '-f', action='store_true', help='Force overwrite existing configuration file')
    parser.add_argument(
        '--with-secrets', '-s', action='store_true', help='Include prompts for sensitive values (email, password)'
    )
    return parser.parse_args()


def write_default_config(config_dir: str, force: bool = False, with_secrets: bool = False):
    """Write default configuration to the specified directory"""
    os.makedirs(config_dir, exist_ok=True)
    config_file = os.path.join(config_dir, "config.yaml")

    if os.path.exists(config_file) and not force:
        print(f"{config_file} already exists. Use --force to overwrite.")
        return

    config = DEFAULT_CONFIG.copy()

    # If with_secrets is enabled, prompt for sensitive values
    if with_secrets:
        print("\nEnter configuration values (press Enter to use defaults):")

        email = input(f"  Email address [{config['ConnectionSettings']['email_address']}]: ").strip()
        if email:
            config['ConnectionSettings']['email_address'] = email

        password = input(f"  App Password [{config['ConnectionSettings']['password']}]: ").strip()
        if password:
            config['ConnectionSettings']['password'] = password

        db_password = input(f"  Database password [{config['MySQL']['password']}]: ").strip()
        if db_password:
            config['MySQL']['password'] = db_password
            # Also update the database section if present
            if 'database' in config:
                config['database']['password'] = db_password

    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, sort_keys=False, default_flow_style=False)

    print(f"✓ Default configuration written to {config_file}")

    # Also create a .env file template if requested
    env_file = os.path.join(config_dir, ".env.template")
    if not os.path.exists(env_file) or force:
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(
                """# PostMaster Environment Variables Template
# Copy this to .env and fill in your values

# Gmail App Password (16 characters with spaces)
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Database Configuration
DB_USER=postmaster_user
DB_PASSWORD=your_password_here
DB_NAME=postmaster_db
DB_HOST=localhost

# OpenRouter API Key (optional)
OPENROUTER_API_KEY=sk-or-v1-xxxxx
"""
            )
        print(f"✓ Environment template written to {env_file}")


def install_to_system():
    """Install configuration to system location /opt/config.d/"""
    print("Installing configuration to /opt/config.d/...")
    try:
        os.makedirs("/opt/config.d", exist_ok=True)
        write_default_config("/opt/config.d", force=False)
        print("✓ Configuration installed to /opt/config.d/config.yaml")
        print("\nTo use this configuration, run:")
        print("  python FrostWardenSanctum.py --config /opt/config.d/config.yaml")
    except PermissionError:
        print("✗ Permission denied. Try running with sudo:")
        print("  sudo python write_config.py --config-dir /opt/config.d")
        sys.exit(1)


if __name__ == "__main__":
    args = parse_args()

    # Special case: install to system location
    if args.config_dir == "/opt/config.d" or args.config_dir == "system":
        install_to_system()
    else:
        write_default_config(args.config_dir, force=args.force, with_secrets=args.with_secrets)
