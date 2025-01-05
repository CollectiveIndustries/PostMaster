"""
This module provides functionality for log rotation, email training, and classification using threading.
It includes classes for log rotation, training emails in batches, and classifying emails based on a trained model.

Classes:
    LogRotation: A thread that monitors and rotates log files when they exceed a given size.
    TrainerThread: A thread that processes emails for training a model in batches.
    ClassificationThread: A thread that classifies emails and moves them to appropriate folders.

Functions:
    split_batches: Splits a total number of items into chunks of a specified batch size.
"""
import threading
import logging
import os
import shutil
import gzip
from datetime import datetime
import time
from .post import PostOffice
from .database import EmailDatabase
from .MailNet import MailNet
from .utils import interruptible_sleep, log_progress
from .config import config

def split_batches(total: int, batch_size: int):
    """
    Process a total number of items in chunks of batch_size.

    Args:
        total (int): The total number of items to process.
        batch_size (int): The size of each batch.

    Yields:
        tuple: The start and end indices of the current batch.
    """
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        yield start, end

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
class TrainerThread(threading.Thread):
    def __init__(
        self, 
        mailbox: tuple[str, str, int],  # Tuple with (source, destination, class_id)
        batch_size: int, 
        stop_event: threading.Event, 
        barrier: threading.Barrier, 
        model_lock: threading.RLock
    ):
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
        """
        Runs the trainer thread for processing emails.

        This method initializes the necessary components for email processing,
        connects to the post office, fetches emails, and processes them in batches.
        It continues to run in a loop until the stop event is set.

        Logging:
            Logs the start and stop of the trainer thread, as well as the progress
            and any errors encountered during execution.

        Raises:
            Exception: If an error occurs during the execution of the thread.

        """
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
                self.post_office.fetch_X_GM_MSGID(self.name)

                total_count = self.email_db.fetch_thread_marker_count(self.name)

                if total_count != 0:
                    logging.info(f"Total emails to process: {total_count} for thread_marker: {self.name}")
                    self._ProcessesBatches_(total_count)
                    logging.info(f"Training on {self.src} emails completed. Waiting for next cycle.")
                else:
                    logging.info(f"No emails to process in {self.src}. Waiting for next cycle.")

                self.wait_barrier() # Wait for thread sync
                interruptible_sleep(self.SleepTime, self.stop_event) # Sleep till next cycle

        except Exception as e:
            logging.error(f"Error in {self.src} trainer thread: {e}", exc_info=True)

        logging.info(f"{self.src} trainer thread stopped.")
        self.wait_barrier()

    def _ProcessesBatches_(self, total_count) -> None:
        """
        Processes batches of emails for training and moves them to the destination folder.

        Args:
            total_count (int): The total number of emails to process.

        The method performs the following steps:
        1. Splits the total count into batches and processes each batch.
        2. Fetches emails for the current batch from the email queue.
        3. Trains the MailNet model using the fetched emails.
        4. Moves the trained emails to the destination folder.
        5. Updates the trained flag and removes the processed emails from the queue.

        The method handles interruptions via a stop event and logs various stages of processing.
        """
        for start, _end_ in split_batches(total_count, self.batch_size):
            if self.stop_event.is_set():
                break
            logging.info(f"Processing batch: {start + 1} to {_end_} out of {total_count}")
            email_batch = []

            for email_id in self.email_db.fetch_mail_from_queue(self.name, self.batch_size):
                if self.stop_event.is_set():
                    break
                try:
                    email = self.post_office.fetch_single_email(email_id)
                    email_batch.append(email)
                except Exception as e:
                    logging.error(f"Failed to fetch email with X-GM-MSGID '{email_id}': {e}")
                    continue

            if not email_batch:
                logging.warning(f"No emails fetched in batch {start + 1} to {_end_}. Skipping.")
                continue

            with self.rlock:
                logging.info(f"Training on {len(email_batch)} {self.src} emails.")
                labels = [self.class_id] * len(email_batch)
                self.mail_net.train(email_batch, labels)
                self.mail_net.save_model()

            trained_msg_ids = []
            logging.info(f"Moving {len(email_batch)} emails to {self.dst}.")
            for email in email_batch:
                try:
                    self.post_office.move(destination_folder=self.dst, x_gm_msgid=email.X_GM_MSGID)
                    self.email_db.add_email_hash(email.hash, email.X_GM_MSGID, self.class_id)
                    self.email_db.log_email_processing(email.X_GM_MSGID, email.hash,self.src, self.dst,"trained")
                    trained_msg_ids.append(email.X_GM_MSGID)
                except Exception as e:
                    logging.error(f"Failed to move email with X-GM-MSGID '{email.X_GM_MSGID}' to {self.dst}: {e}")
                    continue

            if trained_msg_ids:
                try:
                    self.email_db.set_trained_flag(trained_msg_ids)

                    for msg_id in trained_msg_ids:
                        success = self.email_db.pop_from_que(msg_id, self.name)
                        if not success:
                            logging.error(f"Failed to pop email with X-GM-MSGID '{msg_id}' from queue.")
                except Exception as e:
                    logging.error(f"Error during batch processing of trained_msg_ids: {e}", exc_info=True)
            else:
                logging.warning(f"No emails successfully processed in batch {start + 1} to {_end_}.")

        self.post_office.close()
        self.post_office.logout()

    def wait_barrier(self):
        """
        Waits at the barrier until all threads have reached this point.

        This method blocks the calling thread until all threads have called 
        this method. If the barrier is broken, it catches the 
        threading.BrokenBarrierError and prints an error message indicating 
        that the barrier is broken and the thread is exiting.
        """
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

            index = 0
            start_time = time.time()
            total = self.email_db.fetch_thread_marker_count(self.name)
            for start, _end_ in split_batches(total, self.batch_size):
                if self.stop_event.is_set():
                    break
                logging.info(f"Processing batch: {start + 1} to {_end_} out of {total}")

                for email in self.email_db.fetch_mail_from_queue(self.name, self.batch_size):
                    if self.stop_event.is_set():
                        break
                    try:
                        email = self.post_office.fetch_single_email(email)
                        if not email:
                            logging.warning(f"Failed to fetch email with X-GM-MSGID '{email}'. Skipping.")
                            continue

                        class_id = self.mail_net.classify(email)
                        self.email_db.add_email_hash(email.hash, email.X_GM_MSGID, class_id)
                        self.email_db.log_email_processing(email.X_GM_MSGID, email.hash, self.mailbox, config.SPAM_FOLDER if class_id == 0 else config.HAM_FOLDER, "classified")
                        if class_id == 0:
                            self.post_office.move(email.X_GM_MSGID, config.SPAM_FOLDER)
                            logging.debug(f"Email with X-GM-MSGID '{email.X_GM_MSGID}' classified as spam.")
                        else:
                            self.post_office.move(email.X_GM_MSGID, config.HAM_FOLDER)
                            logging.debug(f"Email with X-GM-MSGID '{email.X_GM_MSGID}' classified as ham.")

                        self.email_db.pop_from_que(email.X_GM_MSGID, self.name)

                        if index % 100 == 0:
                            log_progress(index, total, start_time)
                        index += 1

                    except Exception as e:
                        logging.error(f"Failed to fetch email with X-GM-MSGID '{email}': {e}")
                        continue

            self.post_office.close()
            self.post_office.logout()

        logging.info("Shutting down classification thread!")
        self.sync_event.wait()
