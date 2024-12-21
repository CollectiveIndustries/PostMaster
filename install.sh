#!/bin/bash

# Set variables for paths
SERVICE_NAME="spamvanquisher"
SCRIPT_PATH="/opt/spamvanquisher/SpamVanquisher.py"
CONFIG_PATH="/etc/spamvanquisher/config.ini"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
LOG_FILE="/var/log/spamvanquisher.log"
USER_NAME="spamvanquisher"

# Create necessary directories
echo "Creating directories..."
sudo mkdir -p /opt/spamvanquisher
sudo mkdir -p /etc/spamvanquisher
sudo mkdir -p /var/log/spamvanquisher
sudo mkdir -p $LIB_PATH

# Copy the script and configuration file to the proper locations
echo "Copying files..."
sudo cp SpamVanquisher.py $SCRIPT_PATH
sudo cp config.ini $CONFIG_PATH
sudo cp -r lib/* $LIB_PATH

# Create a user and group for the service if they don't exist
echo "Creating user and group for the service..."
sudo useradd --system --no-create-home --group $USER_NAME

# Create the systemd service file
echo "Creating systemd service..."
cat <<EOF | sudo tee $SERVICE_FILE
[Unit]
Description=Spam Vanquisher Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 $SCRIPT_PATH
WorkingDirectory=/opt/spamvanquisher
StandardOutput=file:$LOG_FILE
StandardError=file:$LOG_FILE
Restart=always
User=nobody
Group=nogroup
EnvironmentFile=$CONFIG_PATH

[Install]
WantedBy=multi-user.target
EOF

cat <<EOF | sudo tee $CONFIG_PATH
[ConnectionSettings]
# Email address to monitor for spam and ham learning
email_address = 
# App-specific password generated for this application
password = 

# IMAP server URL for connecting to Gmail
url = imap.gmail.com
# Port number for secure IMAP connection
port = 993

[Folders]
# Folder for spam/ham emails to train the spam filter
spam_learn = Inbox/spam_learn
ham_learn = Inbox/ham_learn

# Destination folders for sorting
spam_folder = Inbox/Spam
ham_folder = Inbox/Ham

# TODO add clamd scanner for additional protection
infected_folder = Inbox/Infected

# Main inbox folder to monitor for filtering
inbox = Inbox

[DaemonSettings]
# Time interval (in seconds) to check and train emails periodically
scan_time = 300

# Data set path. /no/trailing/slash/on/path/to/model
data_path = model

[Logs]
# CRITICAL (50) — Used for very serious errors, usually fatal.
# ERROR (40) — Used for error messages that indicate a problem that prevents the program from continuing as expected.
# WARNING (30) — Used for warning messages that indicate something unexpected or suboptimal but not necessarily an error.
# INFO (20) — Used for general information, typically confirming that things are working as expected.
# DEBUG (10) — Used for detailed information, useful for diagnosing problems.
# NOTSET (0) — The lowest level, which means that all messages will be processed by the logger.
log_level = INFO

# Log file and rotation settings
log_file = logs/SpamVanquisher.log
max_size_mb = 10
backup_count = 5
check_interval = 60
EOF

# Set permissions
echo "Setting permissions..."
sudo chmod 755 $SCRIPT_PATH
sudo chmod 644 $CONFIG_PATH
sudo chmod 644 $SERVICE_FILE
sudo chmod -R 755 $LIB_PATH  # Make sure the lib directory and its contents are executable

# Ensure the log directory is owned by the new user
sudo chown -R $USER_NAME:$USER_NAME /var/log/spamvanquisher

# Reload systemd, enable and start the service
echo "Enabling and starting the service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

# Display the status of the service
echo "Service status:"
sudo systemctl status $SERVICE_NAME
