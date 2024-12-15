import imaplib
from configparser import ConfigParser

# Load global configuration
config = ConfigParser()
config.read('config.ini')

EMAIL = config.get('EmailSettings', 'email_address')
PASSWORD = config.get('EmailSettings', 'password')
URL = config.get('ConnectionSettings', 'url')
PORT = int(config.get('ConnectionSettings', 'port'))
SPAM_LEARN_FOLDER = config.get('Folders', 'spam_learn')
HAM_LEARN_FOLDER = config.get('Folders', 'ham_learn')
INBOX_FOLDER = config.get('Folders', 'inbox')

class PostOffice:
    def __init__(self):
        # Dictionary to store email counts
        self.folder_counts = {}
        # Dictionary to store email data for filtering
        self.emails = {}

    def count_emails(self):
        try:
            # Connect to the Gmail IMAP server
            mail = imaplib.IMAP4_SSL(URL, PORT)
            mail.login(EMAIL, PASSWORD)
            print("Login successful.")

            # List of folders to count emails from
            folders_to_check = [SPAM_LEARN_FOLDER, HAM_LEARN_FOLDER, INBOX_FOLDER]

            for folder in folders_to_check:
                # Attempt to select the folder
                status, response = mail.select(f'"{folder}"')
                if status == "OK":
                    print(f"Successfully selected folder '{folder}'.")
                    status, email_ids = mail.search(None, "ALL")
                    if status == "OK":
                        email_count = len(email_ids[0].split())
                        self.folder_counts[folder] = email_count
                        print(f"Total number of emails in folder '{folder}': {email_count}")
                    else:
                        print(f"Failed to retrieve email IDs from folder '{folder}'.")
                else:
                    print(f"Error selecting folder '{folder}': {response}")

            # Logout from the server
            mail.logout()

        except Exception as e:
            print(f"An error occurred: {e}")

    def get_mail(self, folder_name):
        try:
            # Connect to the Gmail IMAP server
            mail = imaplib.IMAP4_SSL(URL, PORT)
            mail.login(EMAIL, PASSWORD)
            print(f"Login successful for retrieving emails from '{folder_name}'.")

            # Select the specified folder
            status, response = mail.select(f'"{folder_name}"')
            if status == "OK":
                print(f"Successfully selected folder '{folder_name}'.")
                status, email_ids = mail.search(None, "ALL")
                if status == "OK":
                    email_list = email_ids[0].split()
                    self.emails[folder_name] = []
                    for email_id in email_list:
                        status, email_data = mail.fetch(email_id, "(RFC822)")
                        if status == "OK":
                            self.emails[folder_name].append(email_data[0]["RFC822"])
                    print(f"Retrieved {len(self.emails[folder_name])} emails from '{folder_name}'.")
                else:
                    print(f"Failed to retrieve email IDs from folder '{folder_name}'.")
            else:
                print(f"Error selecting folder '{folder_name}': {response}")

            # Logout from the server
            mail.logout()

        except Exception as e:
            print(f"An error occurred while retrieving emails from '{folder_name}': {e}")

# Example usage
if __name__ == "__main__":
    post_office = PostOffice()
    post_office.count_emails()
    print("Folder email counts:", post_office.folder_counts)
    post_office.get_mail(SPAM_LEARN_FOLDER)
    print(f"Retrieved emails from '{SPAM_LEARN_FOLDER}':", len(post_office.emails.get(SPAM_LEARN_FOLDER, [])))
