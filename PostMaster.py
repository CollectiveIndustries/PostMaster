import imaplib
import os
import shutil
from configparser import ConfigParser
import pyclamd
import subprocess
from tqdm import tqdm

class PostOffice:
    def __init__(self):
        # Load configuration from the INI file
        config = ConfigParser()
        config.read('config.ini')

        self.email = config.get('EmailSettings', 'email_address')
        self.password = config.get('EmailSettings', 'password')
        self.url = config.get('ConnectionSettings', 'url')
        self.port = int(config.get('ConnectionSettings', 'port'))
        self.inbox = config.get('Folders', 'inbox')
        
        self.spam_folder = config.get('Folders', 'spam_folder')
        self.ham_folder = config.get('Folders', 'ham_folder')
        self.infected_folder = config.get('Folders', 'infected_folder')

        self.spam_learn = config.get('Folders', 'spam_learn')
        self.ham_learn = config.get('Folders', 'ham_learn')

        # Initialize ClamAV client and SpamAssassin client
        self.clamd_client = pyclamd.ClamdUnixSocket()
        self.spamc_path = "spamc"

        self.emails = {}  # Initialize as an empty dictionary


    def get_mail(self, folder_name):
        """Retrieve emails from a specified folder with a progress bar and store them as a dictionary."""
        try:
            mail = imaplib.IMAP4_SSL(self.url, self.port)
            mail.login(self.email, self.password)
            status, response = mail.select(f'"{folder_name}"')

            if status == "OK":
                status, email_ids = mail.search(None, "ALL")
                if status == "OK":
                    email_ids_list = email_ids[0].split()

                    with tqdm(total=len(email_ids_list), desc="Retrieving emails", unit="email", colour="green") as pbar:
                        for email_id in email_ids_list:
                            status, data = mail.fetch(email_id, "(RFC822)")
                            if status == "OK":
                                for response_part in data:
                                    if isinstance(response_part, tuple):
                                        self.emails[email_id.decode()] = response_part[1]  # Map ID to content
                            pbar.update(1)
                    mail.logout()
                    return True
            mail.logout()
            return False
        except Exception as e:
            print(f"Error retrieving emails from '{folder_name}': {e}")
            return False

    def scan_email(self, email_content):
        """Scan an email using ClamAV and spamc."""
        # Scan with ClamAV
        clamd_result = self.clamd_client.scan_stream(email_content)
        if clamd_result and 'FOUND' in clamd_result.values():
            return 'infected'

        if isinstance(email_content, bytes):  # Convert to str before scan
            email_content = email_content.decode('utf-8', errors='ignore')

        # Scan with spamc
        spamc_result = subprocess.run([self.spamc_path, "-c"], input=email_content, text=True, capture_output=True)

        # Check exit code for spam result
        if spamc_result.returncode == 1:  # 1 indicates spam
            return 'spam'

        # If exit code is 0, it's not spam
        return 'ham'

    def move(self, email_id, source_folder, target_folder):
        """Move an email from one folder to another on the server."""
        try:
            mail = imaplib.IMAP4_SSL(self.url, self.port)
            mail.login(self.email, self.password)

            # Ensure proper folder selection
            status, response = mail.select(source_folder, readonly=False)
            if status != "OK":
                print(f"Failed to select source folder '{source_folder}': {response}")
                return

            # Attempt to copy email to the target folder
            status, response = mail.copy(email_id, target_folder)
            if status != "OK":
                print(f"Failed to copy email {email_id} to '{target_folder}': {response}")
                return

            # Mark the email for deletion in the source folder
            mail.store(email_id, '+FLAGS', '\\Deleted')
            mail.expunge()  # Permanently remove marked emails

        except Exception as e:
            print(f"Error moving email {email_id} from '{source_folder}' to '{target_folder}': {e}")
        finally:
            try:
                mail.logout()
            except:
                pass

    def process_inbox(self):
        """Retrieve and process emails, moving them to appropriate folders."""
        if not self.get_mail(self.inbox):  # Proceed only if emails are successfully retrieved
            print("Failed to retrieve emails. Skipping processing.")
            return

        infected_count = 0
        spam_count = 0
        ham_count = 0

        with tqdm(total=len(self.emails), desc="Processing emails", unit="email", colour="cyan") as pbar:
            for email_id, email_content in self.emails.items():
                scan_result = self.scan_email(email_content)
                if scan_result == 'infected':
                    self.move(email_id, self.inbox, self.infected_folder)
                    infected_count += 1
                elif scan_result == 'spam':
                    self.move(email_id, self.inbox, self.spam_folder)
                    spam_count += 1
                else:
                    self.move(email_id, self.inbox, self.ham_folder)
                    ham_count += 1
                pbar.update(1)

        print("\nSummary:")
        print(f"Infected emails moved: {infected_count}")
        print(f"Spam emails moved: {spam_count}")
        print(f"Ham emails moved: {ham_count}")

    def train_spamc(self):
        """Train spamc with user-flagged spam and ham."""
        try:
            spam_count, ham_count = 0, 0

            # Process spam training emails
            if not self.get_mail(self.spam_learn):
                print(f"Failed to retrieve emails from '{self.spam_learn}'. Skipping spam training.")
            else:
                print(f"Training spamc with flagged spam from '{self.spam_learn}'...")
                with tqdm(total=len(self.emails), desc="Training spam", unit="email", colour="green") as pbar:
                    for email_id, email_content in self.emails.items():
                        spamc_result = subprocess.run(
                            [self.spamc_path, "--learn"], input=email_content, text=True, capture_output=True
                        )
                        if spamc_result.returncode == 0:
                            spam_count += 1
                        else:
                            print(f"Failed to train spamc on spam email ID {email_id}: {spamc_result.stderr}")
                        pbar.update(1)

            # Process ham training emails
            if not self.get_mail(self.ham_learn):
                print(f"Failed to retrieve emails from '{self.ham_learn}'. Skipping ham training.")
            else:
                print(f"Training spamc with flagged ham from '{self.ham_learn}'...")
                with tqdm(total=len(self.emails), desc="Training ham", unit="email", colour="blue") as pbar:
                    for email_id, email_content in self.emails.items():
                        spamc_result = subprocess.run(
                            [self.spamc_path, "--forget"], input=email_content, text=True, capture_output=True
                        )
                        if spamc_result.returncode == 0:
                            ham_count += 1
                        else:
                            print(f"Failed to train spamc on ham email ID {email_id}: {spamc_result.stderr}")
                        pbar.update(1)

            print("\nTraining Summary:")
            print(f"Spam emails trained: {spam_count}")
            print(f"Ham emails trained: {ham_count}")

        except Exception as e:
            print(f"Error during training: {e}")

# Example usage
if __name__ == "__main__":
    post_office = PostOffice()
    post_office.process_inbox()  # Replace with the desired folder name
