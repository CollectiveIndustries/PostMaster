from setuptools import setup
import os
import subprocess

WorkingDirectory = "/opt/spamvanquisher"

# Prompt user for configuration settings
def prompt_user_for_config():
    print("\nConfiguration Settings")
    config = {
        "email_address": input("Enter the email address to monitor for spam and ham learning: "),
        "password": input("Enter the app-specific password for this application: "),
        "imap_url": input("Enter the IMAP server URL (default: imap.gmail.com): ") or "imap.gmail.com",
        "imap_port": input("Enter the IMAP server port (default: 993): ") or "993",
        "spam_learn": input("Enter the spam learning folder path: "),
        "ham_learn": input("Enter the ham learning folder path: "),
        "spam_folder": input("Enter the spam destination folder: "),
        "ham_folder": input("Enter the ham destination folder: "),
        "infected_folder": input("Enter the infected folder path: "),
        "inbox": input("Enter the inbox folder to monitor: "),
        "scan_time": input("Enter the scan interval in seconds (default: 300): ") or "300",
        "log_level": input("Enter the log level (DEBUG, INFO, WARNING, ERROR, CRITICAL, default: INFO): ") or "INFO",
        "data_path": input(f"Enter the path to the dataset directory ({WorkingDirectory}/model): ") or f"{WorkingDirectory}/model",
    }
    return config

# Create configuration file
def create_config_file(config, config_path):
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        f.write("[ConnectionSettings]\n")
        f.write(f"email_address = {config['email_address']}\n")
        f.write(f"password = {config['password']}\n")
        f.write(f"url = {config['imap_url']}\n")
        f.write(f"port = {config['imap_port']}\n")
        f.write("\n[Folders]\n")
        f.write(f"spam_learn = {config['spam_learn']}\n")
        f.write(f"ham_learn = {config['ham_learn']}\n")
        f.write(f"spam_folder = {config['spam_folder']}\n")
        f.write(f"ham_folder = {config['ham_folder']}\n")
        f.write(f"infected_folder = {config['infected_folder']}\n")
        f.write(f"inbox = {config['inbox']}\n")
        f.write("\n[DaemonSettings]\n")
        f.write(f"scan_time = {config['scan_time']}\n")
        f.write(f"data_path = {config['data_path']}\n")
        f.write("\n[Logs]\n")
        f.write(f"log_level = {config['log_level']}\n")

# Create systemd service file
def create_service_file(service_name, script_path, config_path, service_file, log_file):
    os.makedirs(os.path.dirname(service_file), exist_ok=True)
    service_content = f"""[Unit]
Description=Spam Vanquisher Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 {script_path} --config {config_path}
WorkingDirectory={WorkingDirectory}
StandardOutput=file:{log_file}
StandardError=file:{log_file}
Restart=always
User=spamvanquisher
Group=spamvanquisher
EnvironmentFile={config_path}

[Install]
WantedBy=multi-user.target
"""
    with open(service_file, "w") as f:
        f.write(service_content)

# Set up user and group for the service
def setup_user_and_group(user_name):
    try:
        subprocess.run(["sudo", "id", "-u", user_name], check=True)
        print(f"User '{user_name}' already exists.")
    except subprocess.CalledProcessError:
        subprocess.run(["sudo", "useradd", "--system", "--no-create-home", "--group", user_name])
        print(f"User '{user_name}' created successfully.")

# Set permissions and start service
def setup_permissions_and_service(service_name, script_path, config_path, service_file, log_file, user_name):
    subprocess.run(["sudo", "chmod", "755", script_path])
    subprocess.run(["sudo", "chmod", "644", config_path])
    subprocess.run(["sudo", "chmod", "644", service_file])
    subprocess.run(["sudo", "chown", "-R", f"{user_name}:{user_name}", os.path.dirname(log_file)])
    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "enable", service_name])
    subprocess.run(["sudo", "systemctl", "start", service_name])

# Main setup function
def main():
    config_path = "/etc/spamvanquisher/config.ini"
    service_file = "/etc/systemd/system/spamvanquisher.service"
    script_path = f"{WorkingDirectory}/SpamVanquisher.py"
    log_file = "/var/log/spamvanquisher.log"
    user_name = "spamvanquisher"

    # Collect user inputs
    config = prompt_user_for_config()

    # Create necessary directories and files
    os.makedirs(WorkingDirectory, exist_ok=True)
    os.makedirs("/var/log/spamvanquisher", exist_ok=True)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # Create user and group for the service
    setup_user_and_group(user_name)

    # Copy application files
    subprocess.run(["sudo", "cp", "SpamVanquisher.py", script_path])

    # Create configuration and service files
    create_config_file(config, config_path)
    create_service_file("spamvanquisher", script_path, config_path, service_file, log_file)

    # Set permissions and start service
    setup_permissions_and_service("spamvanquisher", script_path, config_path, service_file, log_file, user_name)

    print("Setup completed successfully!")

if __name__ == "__main__":
    main()
