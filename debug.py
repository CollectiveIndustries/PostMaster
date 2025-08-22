#!/user/bin/env /bin/python
import imaplib
import logging
import time

from lib.config import config


class IMAPDebugger:
    def __init__(self):
        self.email = config.EMAIL_ADDRESS
        self.password = config.PASSWORD
        self.mailbox = config.SPAM_LEARN
        self.host = config.IMAP_URL
        self.port = config.IMAP_PORT
        self.mail = None

    def connect(self):
        try:
            self.mail = imaplib.IMAP4_SSL(self.host, self.port)
            self.mail.login(self.email, self.password)
            logging.info("Successfully connected to IMAP server.")
        except Exception as e:
            logging.error(f"Failed to connect to IMAP server: {e}")
            raise

    def select_mailbox(self):
        try:
            result, _ = self.mail.select(self.mailbox)
            if result == 'OK':
                logging.info(f"Mailbox '{self.mailbox}' selected successfully.")
            else:
                logging.error(f"Failed to select mailbox: {self.mailbox}")
                raise Exception("Unable to select mailbox.")
        except Exception as e:
            logging.error(f"Error selecting mailbox: {e}")
            raise

    def fetch_uids(self):
        try:
            result, data = self.mail.uid('search', None, "ALL")
            if result == 'OK':
                uids = data[0].split()
                logging.info(f"Fetched {len(uids)} UIDs from mailbox.")
                return uids
            else:
                logging.error("Failed to fetch UIDs.")
                raise Exception("Unable to fetch UIDs.")
        except Exception as e:
            logging.error(f"Error fetching UIDs: {e}")
            raise

    def fetch_email_by_uid(self, uid):
        try:
            result, data = self.mail.uid('fetch', uid, '(RFC822)')
            if result == 'OK' and data[0]:
                return data[0][1]
            else:
                return None
        except Exception as e:
            logging.error(f"Error fetching email UID {uid.decode()}: {e}")
            return None

    def log_problematic_uids(self, delay: int = 2):
        problematic_uids = []
        uids = self.fetch_uids()

        for uid in uids:
            email_content = self.fetch_email_by_uid(uid)
            if not email_content:
                logging.warning(f"UID {uid.decode()} returned no content.")
                problematic_uids.append(uid.decode())
                time.sleep(delay)  # Avoid throttling

        if problematic_uids:
            logging.info(f"Total problematic UIDs: {len(problematic_uids)}")
            with open("problematic_uids.log", "w") as log_file:
                log_file.write("\n".join(problematic_uids))
            logging.info("Problematic UIDs logged to 'problematic_uids.log'.")
        else:
            logging.info("No problematic UIDs found.")

    def close_connection(self):
        if self.mail:
            self.mail.logout()
            logging.info("Disconnected from IMAP server.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    debugger = IMAPDebugger()
    try:
        debugger.connect()
        debugger.select_mailbox()
        debugger.log_problematic_uids()
    finally:
        debugger.close_connection()
