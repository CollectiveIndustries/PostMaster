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
            logging.error(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                f"Failed to connect to IMAP server: {e}"
            )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
            raise

    def select_mailbox(self):
        try:
            result, _ = self.mail.select(self.mailbox)
            if result == 'OK':
                logging.info(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                    f"Mailbox '{self.mailbox}' selected successfully."
                )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
            else:
                logging.error(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                    f"Failed to select mailbox: {self.mailbox}"
                )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
                raise Exception(  # FIXME pylint: W0719: Raising too general exception: Exception (broad-exception-raised)
                    "Unable to select mailbox."
                )  # FIXME pylint: W0719: Raising too general exception: Exception (broad-exception-raised)  # FIXME pylint: E0011: Unrecognized file option 'broad-exception-raised' (unrecognized-inline-option)
        except Exception as e:
            logging.error(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                f"Error selecting mailbox: {e}"
            )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
            raise

    def fetch_uids(self):
        try:
            result, data = self.mail.uid('search', None, "ALL")
            if (  # FIXME pylint: R1705: Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return)
                result == 'OK'
            ):  # FIXME pylint: R1705: Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return)  # FIXME pylint: E0011: Unrecognized file option 'no-else-return' (unrecognized-inline-option)
                uids = data[0].split()
                logging.info(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                    f"Fetched {len(uids)} UIDs from mailbox."
                )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
                return uids
            else:
                logging.error("Failed to fetch UIDs.")
                raise Exception(  # FIXME pylint: W0719: Raising too general exception: Exception (broad-exception-raised)
                    "Unable to fetch UIDs."
                )  # FIXME pylint: W0719: Raising too general exception: Exception (broad-exception-raised)  # FIXME pylint: E0011: Unrecognized file option 'broad-exception-raised' (unrecognized-inline-option)
        except Exception as e:
            logging.error(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                f"Error fetching UIDs: {e}"
            )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
            raise

    def fetch_email_by_uid(self, uid):
        try:
            result, data = self.mail.uid('fetch', uid, '(RFC822)')
            if (  # FIXME pylint: R1705: Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return)
                result == 'OK' and data[0]
            ):  # FIXME pylint: R1705: Unnecessary "else" after "return", remove the "else" and de-indent the code inside it (no-else-return)  # FIXME pylint: E0011: Unrecognized file option 'no-else-return' (unrecognized-inline-option)
                return data[0][1]
            else:
                return None
        except Exception as e:
            logging.error(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                f"Error fetching email UID {uid.decode()}: {e}"
            )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
            return None

    def log_problematic_uids(self, delay: int = 2):
        problematic_uids = []
        uids = self.fetch_uids()

        for uid in uids:
            email_content = self.fetch_email_by_uid(uid)
            if not email_content:
                logging.warning(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                    f"UID {uid.decode()} returned no content."
                )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
                problematic_uids.append(uid.decode())
                time.sleep(delay)  # Avoid throttling

        if problematic_uids:
            logging.info(  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)
                f"Total problematic UIDs: {len(problematic_uids)}"
            )  # FIXME pylint: W1203: Use lazy % formatting in logging functions (logging-fstring-interpolation)  # FIXME pylint: E0011: Unrecognized file option 'logging-fstring-interpolation' (unrecognized-inline-option)
            with open(  # FIXME pylint: W1514: Using open without explicitly specifying an encoding (unspecified-encoding)
                "problematic_uids.log", "w"
            ) as log_file:  # FIXME pylint: W1514: Using open without explicitly specifying an encoding (unspecified-encoding)  # FIXME pylint: E0011: Unrecognized file option 'unspecified-encoding' (unrecognized-inline-option)
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
