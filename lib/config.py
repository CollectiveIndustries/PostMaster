import configparser
import getpass
import grp
import hashlib
import logging
import argparse
import os
import pwd
import random
import subprocess
import time
import string

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
        self.UNSORTED = CONFIG.get('Folders', 'unsorted')
        self.INFECTED_FOLDER = CONFIG.get('Folders', 'infected_folder')
        self.SPAM_LEARN = CONFIG.get('Folders', 'spam_learn')
        self.HAM_LEARN = CONFIG.get('Folders', 'ham_learn')

        # Daemon Settings
        self.TRAINING_DATA_PATH = CONFIG.get('DaemonSettings', 'data_path')
        self.SCAN_TIME = int(CONFIG.get('DaemonSettings', 'scan_time'))
        self.BATCH_SIZE = int(CONFIG.get('DaemonSettings', 'batch_size', fallback=100))

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

        # MySQL Database settings for hashtable
        self.SQL_USER = CONFIG.get('MySQL','user', fallback='SpamVanquisher')
        self.SQL_HOST = CONFIG.get('MySQL','host', fallback='127.0.0.1')
        self.SQL_DATABASE = CONFIG.get('MySQL','database', fallback='SpamVanquisher')
        self.SQL_PASSWORD = CONFIG.get('MySQL','password')
        self.SQL_PORT = int(CONFIG.get('MySQL','port',fallback=3306))

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

# config_template.ini
"""Template configuration file for SpamVanquisher."""

TEMPLATE = """[ConnectionSettings]
# Email address to monitor for spam and ham learning
email_address = {email_address}

# App-specific password generated for this application
password = {password}

# IMAP server URL for connecting to Gmail
url = {url}

# Port number for secure IMAP connection
port = {port}

[Folders]
# Folder for spam/ham emails to train the spam filter
spam_learn = {spam_learn}
ham_learn = {ham_learn}

# Destination folders for sorting
spam_folder = {spam_folder}
ham_folder = {ham_folder}

# TODO add clamd scanner for additional protection
infected_folder = {infected_folder}

# Main inbox folder to monitor for filtering
inbox = {inbox}

[DaemonSettings]
# Time interval (in seconds) to check and train emails periodically
scan_time = {scan_time}

# Data set path. /no/trailing/slash/on/path/to/model
data_path = {data_path}

# Batch size determines amount of mail per batch that will be fetched, trained, and moved in bulk operations
batch_size = {batch_size}

[Logs]
# Logging levels
log_level = {log_level}

# Log file and rotation settings
log_file = {log_file}
max_size_mb = {max_size_mb}
backup_count = {backup_count}
check_interval = {check_interval}

[EmailParts]
# These settings change the NN Model to include parts of the email for learning/classifying
use_subject = {use_subject}
use_sender = {use_sender}
use_recipient = {use_recipient}
use_body = {use_body}

[MySQL]
# MySQL database connection settings
host = {mysql_host}
user = {mysql_user}
password = {mysql_password}
database = {mysql_database}
port = {mysql_port}
"""

def generate_random_password(length: int = 32) -> str:
    """
    Generate a random password with the specified length using a time-based seed and a more complex salt.

    :param length: Length of the password to generate (default is 32)
    :return: A randomly generated password string
    """
    # Use the current time to generate a unique seed
    seed = int(time.time() * 1000)  # Milliseconds for higher precision
    random.seed(seed)

    # Generate a more complex salt
    # Combine current time, random bytes, and a hash to create a unique and complex salt
    salt_base = f"{seed}-{os.urandom(16).hex()}-{random.randint(0, 1000000)}"
    salt = hashlib.sha256(salt_base.encode()).hexdigest()  # Apply SHA-256 for better complexity

    # Define the character set for the password
    characters = string.ascii_letters + string.digits + string.punctuation
    
    # Generate the password by selecting random characters
    password = ''.join(random.choice(characters) for _ in range(length))
    
    # Mix the salt with the password to ensure it's more unique
    salted_password = ''.join(random.choice(salt + password) for _ in range(length))
    
    return salted_password

SERVICE_NAME = "SpamVanquisher"
INSTALL_DIR = f"/opt/{SERVICE_NAME}"
CONFIG_DIR = f"/etc/{SERVICE_NAME}"
LOG_DIR = f"/var/log/{SERVICE_NAME}"
USER = "spamvanquisher"
GROUP = "spamvanquisher"
DB_SCRIPT = "install.sql"
DB_NAME = "SpamVanquisher"
DB_USER = "PostMan"
DATABASE_PASSWORD = generate_random_password()

def get_user_input(prompt, default=None, required=False, is_password=False, type_cast=None):
    """
    Helper function to get user input with options for default values, type casting, and password masking.
    
    :param prompt: Prompt message for the user
    :param default: Default value if the user provides no input
    :param required: Whether the input is required (cannot be empty)
    :param is_password: Whether to mask input as a password
    :param type_cast: A function to cast input to a specific type (e.g., int, float)
    :return: The validated input value
    """
    while True:
        if is_password:
            value = getpass.getpass(f"{prompt} [{'default=' + str(default) if default else ''}]: ").strip()
        else:
            value = input(f"{prompt} [{'default=' + str(default) if default else ''}]: ").strip()

        if not value and default is not None:
            value = default

        if not value and required:
            print("This field is required. Please provide a value.")
            continue

        if type_cast:
            try:
                value = type_cast(value)
            except ValueError:
                print(f"Invalid value. Please enter a valid {type_cast.__name__}.")
                continue

        return value


def generate_config_file(output_path):
    """
    Generate a configuration file based on user input.
    
    :param output_path: Path where the configuration file should be saved
    """
    config_data = {
        "email_address": get_user_input("Enter email address to monitor", required=True),
        "password": get_user_input("Enter app-specific password", required=True, is_password=True),
        "url": get_user_input("Enter IMAP server URL", "imap.gmail.com"),
        "port": get_user_input("Enter IMAP server port", "993", type_cast=int),
        "spam_learn": get_user_input("Enter spam learn folder path", "Inbox/spam_learn"),
        "ham_learn": get_user_input("Enter ham learn folder path", "Inbox/ham_learn"),
        "spam_folder": get_user_input("Enter spam folder path", "Inbox/Spam"),
        "ham_folder": get_user_input("Enter ham folder path", "Inbox/Ham"),
        "infected_folder": get_user_input("Enter infected folder path", "Inbox/Infected"),
        "inbox": get_user_input("Enter main inbox folder path", "Inbox"),
        "scan_time": get_user_input("Enter scan time interval (seconds)", "300", type_cast=int),
        "data_path": get_user_input("Enter model data path", "model"),
        "batch_size": get_user_input("Enter batch size", "200", type_cast=int),
        "log_level": get_user_input("Enter logging level", "INFO"),
        "log_file": get_user_input("Enter log file path", "logs/SpamVanquisher.log"),
        "max_size_mb": get_user_input("Enter max log file size (MB)", "10", type_cast=int),
        "backup_count": get_user_input("Enter number of backup logs", "5", type_cast=int),
        "check_interval": get_user_input("Enter log rotation check interval (seconds)", "60", type_cast=int),
        "use_subject": get_user_input("Use email subject for training? (true/false)", "true"),
        "use_sender": get_user_input("Use email sender for training? (true/false)", "true"),
        "use_recipient": get_user_input("Use email recipient for training? (true/false)", "false"),
        "use_body": get_user_input("Use email body for training? (true/false)", "true"),
        "mysql_host": get_user_input("Enter MySQL host", "127.0.0.1"),
        "mysql_user": get_user_input("Enter MySQL username", "PostMan"),
        "mysql_password": get_user_input("Enter MySQL password", required=True, is_password=True, default=DATABASE_PASSWORD),
        "mysql_database": get_user_input("Enter MySQL database", "SpamVanquisher"),
        "mysql_port": get_user_input("Enter MySQL port", "3306", type_cast=int),
    }

    config_content = TEMPLATE.format(**config_data)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as config_file:
        config_file.write(config_content)
    print(f"Configuration file saved to {output_path}")

def create_user_and_group(service_name, group_name, user_name, install_dir):
    print(f"Creating user and group for {service_name}...")

    try:
        # Check if group exists, create if not
        try:
            grp.getgrnam(group_name)
            print(f"Group '{group_name}' already exists.")
        except KeyError:
            print(f"Creating system group '{group_name}'...")
            subprocess.run(["groupadd", "--system", group_name], check=True)

        # Check if user exists, create if not
        try:
            pwd.getpwnam(user_name)
            print(f"User '{user_name}' already exists.")
        except KeyError:
            print(f"Creating system user '{user_name}'...")
            subprocess.run([
                "useradd", "--system", "--home-dir", install_dir,
                "--shell", "/usr/sbin/nologin", "--gid", group_name, user_name
            ], check=True)

        print(f"User and group setup completed for {service_name}.")
    except subprocess.CalledProcessError as e:
        print(f"Error while creating user or group: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def create_directories(install_dir, config_dir, log_dir, user, group):
    print("Creating directories...")

    directories = {
        "install_dir": install_dir,
        "config_dir": config_dir,
        "log_dir": log_dir
    }
    
    try:
        # Create directories and apply ownership/permissions
        for name, path in directories.items():
            print(f"Creating directory: {path}")
            os.makedirs(path, exist_ok=True)
            
            print(f"Setting ownership for {path} to {user}:{group}...")
            subprocess.run(["chown", "-R", f"{user}:{group}", path], check=True)
            
            print(f"Setting permissions for {path} to 750...")
            subprocess.run(["chmod", "-R", "750", path], check=True)
        
        print("All directories created and permissions set successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error while setting ownership or permissions: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def setup_database(db_script, db_name, db_user, db_password):
    """
    Set up a MySQL database by creating the database, user, and applying schema.
    
    :param db_script: Path to the SQL script for schema initialization
    :param db_name: Name of the database to create
    :param db_user: Database user to create
    :param db_password: Password for the database user
    """
    db_script = os.path.abspath(db_script)  # Resolve absolute path
    if not os.path.isfile(db_script):
        print(f"Error: SQL script file '{db_script}' does not exist.")
        return

    print("Setting up MySQL database...")

    try:
        # Create database and user
        create_db_commands = f"""
        CREATE DATABASE IF NOT EXISTS {db_name};
        CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{db_password}';
        GRANT ALL PRIVILEGES ON {db_name}.* TO '{db_user}'@'localhost';
        FLUSH PRIVILEGES;
        """
        subprocess.run(
            ["mysql", "-u", "root", "-p"],  # Prompts for root password
            input=create_db_commands,
            text=True,
            check=True
        )
        print(f"Database '{db_name}' and user '{db_user}' setup completed.")

        # Load the SQL file into the database
        load_schema_command = f"mysql -u root -p {db_name} < {db_script}"
        subprocess.run(load_schema_command, shell=True, check=True)

        print(f"Database schema from '{db_script}' applied successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error during database setup: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def create_systemd_service(service_name, user, group, install_dir, script_name="run.sh"):
    """
    Create a systemd service file and enable the service.

    :param service_name: Name of the service
    :param user: User under which the service will run
    :param group: Group under which the service will run
    :param install_dir: Directory where the service is installed
    :param script_name: The script to execute when starting the service
    """
    service_file_content = f"""[Unit]
Description={service_name} Service
After=network.target

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={install_dir}
ExecStart={install_dir}/{script_name}
Restart=always
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier={service_name}

[Install]
WantedBy=multi-user.target
"""

    service_file_path = f"/etc/systemd/system/{service_name}.service"
    
    try:
        # Ensure the target directory exists and has proper permissions
        if not os.path.exists(install_dir):
            print(f"Error: Install directory '{install_dir}' does not exist.")
            return
        
        # Write the service file content
        print(f"Writing systemd service file to {service_file_path}...")
        with open(service_file_path, "w") as service_file:
            service_file.write(service_file_content)

        # Reload systemd and enable the service
        print("Reloading systemd daemon and enabling the service...")
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", service_name], check=True)

        print(f"Systemd service for {service_name} created and enabled successfully!")
        
    except subprocess.CalledProcessError as e:
        print(f"Error during systemd service setup: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def install():
    # Create user and group
    create_user_and_group(SERVICE_NAME, GROUP, USER, INSTALL_DIR)

    # Create necessary directories
    create_directories(INSTALL_DIR, CONFIG_DIR, LOG_DIR, USER, GROUP)

    # Setup the database
    setup_database(DB_SCRIPT, DB_NAME, DB_USER, DATABASE_PASSWORD)

    # Create the systemd service
    create_systemd_service(SERVICE_NAME, USER, GROUP, INSTALL_DIR)

    # Generate the configuration file
    generate_config_file("/path/to/config.ini")

    print("Installation complete!")

# Parse arguments
args = parse_args()

# Pass the config file path to the conf class
config = conf(config_file=args.config)