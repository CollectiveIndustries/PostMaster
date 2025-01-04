import threading
import logging
import time
import os
import shutil
import gzip
from datetime import datetime
from .post import PostOffice
from .database import EmailDatabase
from .MailNet import MailNet
from .utils import interruptible_sleep
from .config import config

class LogRotation(threading.Thread):
    def __init__(self, stop_event: threading.Event):
        """
        Thread to monitor and rotate log files when they exceed a given size.
        """
        super().__init__(name="LogRotationThread")
        self.daemon = True
        self.log_file = config.LOG_FILE
        self.backup_count = config.BACKUP_COUNT
        self.check_interval = config.CHECK_INTERVAL
        self.stop_event = stop_event
        logging.info("Log rotation thread intilized.")

    def run(self):
        log_file = config.LOG_FILE
        logging.info("Log rotation thread started. Monitoring file: %s", log_file)
        while not self.stop_event.is_set():
            try:
                if os.path.exists(log_file):
                    file_size = os.path.getsize(log_file)
                    logging.debug(f"Current log file size: {file_size} bytes. MAX_SIZE: {config.MAX_SIZE}")
                    if file_size >= config.MAX_SIZE:
                        logging.warning(f"Log file size exceeded threshold: {log_file}")
                        self.rotate()
                else:
                    with open(log_file, 'w') as log_file:
                        log_file.write("")  # Initialize an empty log file
            except Exception as e:
                logging.error("Error in log rotation thread: %s", e, exc_info=True)
            interruptible_sleep(config.CHECK_INTERVAL, self.stop_event)
        logging.info("Log rotation thread stopped.")

    def start(self):
        logging.info("Starting LogRotationThread...")
        super().start()

    def stop(self):
        """Stops the log rotation thread."""
        logging.info("Stopping log rotation thread...")

    def rotate(self):
        """Handles rotating the log files based on daily, weekly, and monthly retention rules."""
        logging.info("Rotating logs for file: %s", self.log_file)

        try:
            now = datetime.now()

            # Define log rotation file suffixes
            daily_suffix = now.strftime("%Y-%m-%d")
            weekly_suffix = f"week-{now.strftime('%U')}-{now.year}"
            monthly_suffix = now.strftime("%Y-%m")

            # Define paths for the rotated logs
            daily_log = f"{self.log_file}.{daily_suffix}.gz"
            weekly_log = f"{self.log_file}.{weekly_suffix}.gz"
            monthly_log = f"{self.log_file}.{monthly_suffix}.gz"

            # Compress and archive the current log file as a daily log
            if os.path.exists(self.log_file):
                with open(self.log_file, 'rb') as f_in:
                    with gzip.open(daily_log, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                logging.info("Archived current log file as daily log: %s", daily_log)
                # Clear the current log file
                open(self.log_file, 'w').close()

            # Manage weekly and monthly logs
            if now.weekday() == 0:  # If it's Monday, create a weekly log
                if not os.path.exists(weekly_log):
                    shutil.copy(daily_log, weekly_log)
                    logging.info("Archived weekly log: %s", weekly_log)

            if now.day == 1:  # If it's the first day of the month, create a monthly log
                if not os.path.exists(monthly_log):
                    shutil.copy(daily_log, monthly_log)
                    logging.info("Archived monthly log: %s", monthly_log)

            # Retention cleanup: daily logs (7 days), weekly logs (3 months), monthly logs (1–2 years)
            self._cleanup_logs(self.log_file, "daily", 7)
            self._cleanup_logs(self.log_file, "week", 12)
            self._cleanup_logs(self.log_file, "monthly", 24)

        except Exception as e:
            logging.error("Failed to rotate logs: %s", e, exc_info=True)
            logging.critical("Critical failure during log rotation.")

    def _cleanup_logs(self, log_file_base, period, retention_count):
        """
        Deletes old rotated log files based on the given retention count and period type.

        Args:
            log_file_base (str): The base name of the log file.
            period (str): The rotation period (e.g., "daily", "week", "monthly").
            retention_count (int): The maximum number of logs to retain for the period.
        """
        try:
            all_logs = sorted([
                f for f in os.listdir(".")
                if f.startswith(log_file_base) and period in f
            ])

            # Retain only the most recent logs up to retention_count
            if len(all_logs) > retention_count:
                for old_log in all_logs[:len(all_logs) - retention_count]:
                    os.remove(old_log)
                    logging.info("Removed old log file: %s", old_log)

        except Exception as e:
            logging.error("Failed to clean up old logs for period '%s': %s", period, e, exc_info=True)

# Initialize classes
# post_office = PostOffice()
# email_db = EmailDatabase()
# mail_net = MailNet()
# 
# ClassificationThread definition
# classification_thread = ClassificationThread(post_office, email_db, mail_net, stop_event)

class TrainerThread(threading.Thread):
    def __init__(self, mailbox: tuple, batch_size: int, stop_event: threading.Event, barrier: threading.Barrier, model_lock: threading.RLock):
        super().__init__()
        self.src, self.dst, self.class_id = mailbox
        self.batch_size = batch_size
        self.stop_event = stop_event
        self.rlock = model_lock
        self.barrier = barrier
        self.SleepTime = config.SCAN_TIME

    def stop(self):
        self.stop_event.set()

    def run(self):
        logging.info(f"Starting {self.src} trainer thread.")
        self.name = threading.current_thread().name
        self.post_office = PostOffice(self.stop_event, self.src)
        self.email_db = EmailDatabase()
        self.mail_net = MailNet()

        self.email_db.add_folder_and_classification(self.class_id, self.dst)

        try:
            while not self.stop_event.is_set():
                self.post_office.connect()
                self.post_office.select_box(readonly=False)

                logging.info(f"Fetching list of mail from {self.src}")
                # Step 1: Fetch all x_gm_msgid with the PostOffice class
                # Step 2: Update mail_que in the EmailDatabase class
                self.post_office.fetch_X_GM_MSGID(self.name)

                # Step 3: Set up a loop to fetch from mail_que in the EmailDatabase class
                batch_msg_ids = self.email_db.fetch_mail_from_queue(self.name, self.batch_size)

                if not batch_msg_ids:
                    logging.info(f"No unprocessed {self.src} emails found. Sleeping.")
                    self.wait_barrier()
                    time.sleep(self.SleepTime)
                    continue

                # Step 4: Fetch batch using x_gm_msgid from PostOffice
                email_batch = []
                try:
                    # Use the fetch_batch method to fetch emails based on batch_msg_ids
                    for email in self.post_office.fetch_batch(batch_msg_ids):
                        if email:
                            email_batch.append(email)
                except Exception as e:
                    logging.error(f"Error while fetching email batch: {e}")

                # If batch is empty, skip further processing
                if not email_batch:
                    logging.warning(f"Failed to fetch emails for IDs: {batch_msg_ids}")
                    continue

                # Step 5: Train batch using MailNet class
                with self.rlock:
                    logging.info(f"Training on {len(email_batch)} {self.src} emails.")
                    labels = [self.class_id] * len(email_batch)  
                    self.mail_net.train(email_batch, labels)
                    self.mail_net.save_model()

                # Step 6: Move batch with PostOffice class
                logging.info(f"Moving {len(email_batch)} emails to {self.dst} folder.")

                # Move each email using the X-GM-MSGID from the email object
                for email in email_batch:
                    try:
                        self.post_office.move(destination_folder=self.dst, x_gm_msgid=email.X_GM_MSGID)
                    except Exception as e:
                        logging.error(f"Failed to move email with X-GM-MSGID '{email.X_GM_MSGID}' to {self.dst}: {e}")

                # Step 7: Set trained_flag in the EmailDatabase class
                trained_msg_ids = [email.msg_id for email in email_batch]
                self.email_db.set_trained_flag(trained_msg_ids)

                # Step 8: Pop from mail_que in EmailDatabase class
                self.email_db.pop_from_que(trained_msg_ids, self.name)

                self.post_office.close()
                self.post_office.logout()

                self.wait_barrier() # Wait for thread sync

        except Exception as e:
            logging.error(f"Error in {self.src} trainer thread: {e}", exc_info=True)

        logging.info(f"{self.src} trainer thread stopped.")

    def wait_barrier(self):
        try:
            self.barrier.wait()
        except threading.BrokenBarrierError:
            print(f"{self.name} barrier broken, exiting.")

class ClassificationThread(threading.Thread):
    def __init__(self, mailbox: str, stop_event: threading.Event, sync_event: threading.Barrier, batch_size: int):
        super().__init__()
        self.mailbox = mailbox  # 'inbox' or another mailbox for classification
        self.batch_size = batch_size
        self.stop_event = stop_event
        self.sync_event = sync_event

    def run(self):
        self.mail_net = MailNet()
        self.email_db = EmailDatabase()
        self.post_office = PostOffice(self.stop_event, self.mailbox)
        self.name = threading.current_thread().name

        while not self.stop_event.is_set():
            # Wait for sync_event to ensure training threads have completed
            self.sync_event.wait()

            self.post_office.connect()
            self.post_office.select_box(readonly=False)

            # Fetch X-GM-MSGIDs from the mail_que (the queue of unprocessed emails)
            self.post_office.fetch_X_GM_MSGID(self.name)

            x_gm_msgids = self.email_db.fetch_mail_from_queue(self.batch_size,self.name)
            if not x_gm_msgids:
                continue

            # Fetch the emails using the X-GM-MSGIDs
            email_batch = self.post_office.fetch_batch(x_gm_msgids)

            # Classify the emails using the model
            classifications = self.mail_net.classify(email_batch)

            # Process the classifications: move the email to the appropriate folder
            for msgid, label in zip(x_gm_msgids, classifications):
                target_folder = "spam" if label == 1 else "ham"

                # Move email to the target folder
                self.post_office.move(msgid, target_folder)

                # Remove the email from the queue as it's processed
                self.email_db.pop_from_que(msgid,self.name)

            self.post_office.close()
            self.post_office.logout()

        logging.info("Shutting down classification thread!")
