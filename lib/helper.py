import configparser
import os

def generate_config(file_path="config.ini"):
    config = configparser.ConfigParser()

    # ConnectionSettings section
    config['ConnectionSettings'] = {
        'email_address': '',
        'password': '',
        'url': 'imap.gmail.com',
        'port': '993'
    }

    # Folders section
    config['Folders'] = {
        'spam_learn': 'spam_learn',
        'ham_learn': 'ham_learn',
        'spam_folder': 'Spam',
        'ham_folder': 'Ham',
        'infected_folder': 'Infected',
        'inbox': 'Inbox'
    }

    # DaemonSettings section
    config['DaemonSettings'] = {
        'scan_time': '300',
        'data_path': 'model'  # Ensure this directory exists
    }

    # Logs section
    config['Logs'] = {
        'log_level': 'INFO',
        'log_file': 'logs/SpamVanquisher.log', # Ensure this directory exists
        'max_size_mb': '10',
        'backup_count': '5',
        'check_interval': '60'
    }

    # Create necessary directories if they don't exist
    log_dir = os.path.dirname(file_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Ensure the data_path exists
    data_path = config['DaemonSettings']['data_path']
    if not os.path.exists(data_path):
        os.makedirs(data_path)
        print(f"Created data path directory: {data_path}")

    # Write the configuration to a file
    with open(file_path, 'w') as configfile:
        config.write(configfile)
    print(f"Configuration written to {file_path}")

# Call the function to generate the config.ini file
if not os.path.exists("config.ini"):
    generate_config()
