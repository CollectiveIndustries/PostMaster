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
import pickle
import threading
import logging
import os
import shutil
import gzip
from datetime import datetime
import time
from .post import PostOffice, Email
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

class ThreadBase(threading.Thread):
    def __init__(self, name: str, mailbox: str | tuple[str, str, int], stop_event: threading.Event, barrier: threading.Barrier, batch_size: int):
        """
        Base class for threads that manage mail processing tasks.

        Args:
            mailbox (str | tuple): Mailbox string ('inbox') or tuple (source, destination, class_id).
            batch_size (int): The batch size for processing.
            stop_event (threading.Event): Event to signal when the thread should stop.
            barrier (threading.Barrier): Synchronization barrier for coordinating thread activity.
        """
        super().__init__()
        self.mailbox = mailbox  # Either a string or a tuple
        self.batch_size = batch_size
        self.stop_event = stop_event
        self.barrier = barrier

        self.email_db = EmailDatabase()
        self.mail_net = MailNet()

        self.post_office = None

        self.name = name
        self.daemon = True

    def stop(self):
        """
        Signals the thread to stop and cleans up resources.
        """
        logging.info(f"Stopping thread: {self.name}")
        self.stop_event.set()  # Signal the thread to stop
        self.CleanUpConnections()

    def CleanUpConnections(self):
        """
        Cleans up the connections to email server, database, and model resources.
        """
        try:
            if self.email_db:
                logging.info("Closing database connection...")
                self.email_db.close()
        except Exception as e:
            logging.error(f"Error closing database connection: {e}", exc_info=True)

        try:
            if self.post_office:
                logging.info("Closing IMAP connection...")
                self.post_office.close()
                self.post_office.logout()
        except Exception as e:
            logging.error(f"Error closing IMAP connection: {e}", exc_info=True)

        try:
            if self.mail_net and hasattr(self.mail_net, "unload_model"):
                logging.info("Unloading TensorFlow model...")
                self.mail_net.unload_model()
        except Exception as e:
            logging.error(f"Error unloading TensorFlow model: {e}", exc_info=True)

    def ThreadSleep(self):
        """
        Sleeps the thread till all the threads have reached the barrier.
        Cleans up all connections before sleeping.
        """
        self.CleanUpConnections()
        self.mail_net.unload_model()
        try:
            self.barrier.wait()
        except threading.BrokenBarrierError:
            print(f"{self.name} barrier broken, exiting.")

class TrainerThread(ThreadBase):
    def __init__(
        self, 
        name: str,
        mailbox: tuple[str, str, int],  # Tuple with (source, destination, class_id)
        stop_event: threading.Event, 
        barrier: threading.Barrier, 
        model_lock: threading.RLock,
        batch_size: int
    ):
        super().__init__(name, mailbox, stop_event, barrier, batch_size)
        self.src, self.dst, self.class_id = mailbox
        self.rlock = model_lock
        self.SleepTime = config.SCAN_TIME

        self.post_office = PostOffice(stop_event, self.src)

    def run(self):
        logging.info(f"[{self.name}] Trainer thread for '{self.src}' started.")
        self.post_office = PostOffice(self.stop_event, self.src)

        self.email_db.add_folder_and_classification(self.class_id, self.dst)

        try:
            while not self.stop_event.is_set():
                logging.info(f"[{self.name}] Checking IMAP state and database connectivity.")
                self.post_office.check_imap_state(readonly=False)
                self.email_db.check_and_reconnect()

                # Fetch emails from IMAP
                logging.info(f"[{self.name}] Fetching email message IDs from '{self.src}'.")
                total = self.post_office.total_emails(self.src)
                index = 0

                for batch in self.post_office.fetch_X_GM_MSGID(self.batch_size):
                    self.email_db.update_mail_queue(self.name, batch)
                    log_progress(len(batch) + index, total, time.time(), stage="Fetching emails")
                    index += len(batch)

                # Check if there are emails to process
                total_count = self.email_db.fetch_thread_marker_count(self.name)

                if total_count > 0:
                    logging.info(f"[{self.name}] Total emails to process: {total_count}. Beginning training cycle.")
                    self.mail_net.load_model()
                    self._ProcessesBatches_(total_count)
                    logging.info(f"[{self.name}] Training completed. Waiting for next cycle.")
                else:
                    logging.info(f"[{self.name}] No emails to process in '{self.src}'. Waiting for the next cycle.")

                self.ThreadSleep()
                interruptible_sleep(self.SleepTime, self.stop_event)

        except Exception as e:
            logging.error(f"[{self.name}] Error in trainer thread: {e}", exc_info=True)

        logging.info(f"[{self.name}] Trainer thread stopped. Waiting for other threads to finish.")
        self.ThreadSleep()

    def _ProcessesBatches_(self, total_count) -> None:
        for start, _end_ in split_batches(total_count, self.batch_size):
            if self.stop_event.is_set():
                break

            logging.info(f"[{self.name}] Processing batch {start + 1} to {_end_} out of {total_count}.")

            email_batch = []
            x_gm_msgids = list(self.email_db.fetch_mail_from_queue(self.name, total_count))

            if not x_gm_msgids:
                logging.debug(f"[{self.name}] No more emails in the queue to process.")
                break

            start_time = time.time()

            # Fetch emails in bulk
            for email in self.post_office.fetch_batch(x_gm_msgids, self.batch_size):
                if self.stop_event.is_set():
                    break
                email_batch.append(email)

                if len(email_batch) >= self.batch_size:
                    logging.info(f"[{self.name}] Full batch fetched. Processing {len(email_batch)} emails.")
                    self.process_batch(email_batch)
                    email_batch = []  # Reset the batch

            if email_batch:  # Process remaining emails
                logging.info(f"[{self.name}] Processing the final batch of {len(email_batch)} emails.")
                self.process_batch(email_batch)

            log_progress(len(email_batch), len(x_gm_msgids), start_time, stage="Training emails")

    def process_batch(self, email_batch: list[Email]) -> None:
        logging.info(f"[{self.name}] Starting model training for {len(email_batch)} emails.")
        try:
            with self.rlock:  # Ensure thread-safe model access
                # Tokenizer and model training
                email_texts = [email.text() for email in email_batch]
                self.mail_net.fit_tokenizer(email_texts)
                labels = [self.class_id] * len(email_batch)
                self.mail_net.train(email_batch, labels)
                self.mail_net.save_model()

                with open(f"{config.TRAINING_DATA_PATH}/tokenizer.pkl", "wb") as f:
                    pickle.dump(self.mail_net.tokenizer, f)

            logging.info(f"[{self.name}] Model training completed for this batch.")

        except Exception as e:
            logging.error(f"[{self.name}] Error during model training: {e}", exc_info=True)

        # Move emails and update database
        trained_msg_ids = []
        logging.info(f"[{self.name}] Moving processed emails to '{self.dst}' and updating the database.")
        for email in email_batch:
            try:
                self.post_office.move(destination_folder=self.dst, x_gm_msgid=email.X_GM_MSGID)
                self.email_db.add_email_hash(email.hash, email.X_GM_MSGID, self.class_id)
                self.email_db.log_email_processing(email.X_GM_MSGID, email.hash, self.src, self.dst, "trained")
                self.email_db.set_trained_flag([email.X_GM_MSGID])
                success = self.email_db.pop_from_que(email.X_GM_MSGID, self.name)

                if not success:
                    logging.error(f"[{self.name}] Failed to pop email with X-GM-MSGID '{email.X_GM_MSGID}' from queue.")

                trained_msg_ids.append(email.X_GM_MSGID)

            except Exception as e:
                logging.error(f"[{self.name}] Failed to process email with X-GM-MSGID '{email.X_GM_MSGID}': {e}", exc_info=True)

        if trained_msg_ids:
            logging.info(f"[{self.name}] Successfully processed {len(trained_msg_ids)} emails in this batch.")
        else:
            logging.warning(f"[{self.name}] No emails were successfully processed in this batch.")

class ClassificationThread(ThreadBase):
    def __init__(self, name: str, mailbox: str, stop_event: threading.Event, barrier: threading.Barrier, batch_size: int):
        """
        Thread for classifying emails in a mailbox.

        Args:
            mailbox (str): The mailbox to classify emails from.
            stop_event (threading.Event): Event to signal when the thread should stop.
            sync_event (threading.Barrier): Synchronization barrier for coordinating thread activity.
            batch_size (int): The batch size for classification.
        """
        super().__init__(name, mailbox, stop_event, barrier, batch_size)

        self.post_office = PostOffice(stop_event, mailbox)

    def run(self):

        while not self.stop_event.is_set():
            # Wait for sync_event to ensure training threads have completed
            self.ThreadSleep()

            self.mail_net.load_model()
            self.email_db.check_and_reconnect()

            self.post_office.connect()
            self.post_office.select_box(readonly=False)

            # Fetch X-GM-MSGIDs from the mail_que (the queue of unprocessed emails)
            logging.info(f"Fetching list of mail from '{self.mailbox}'")
            total = self.post_office.total_emails(self.mailbox)
            index = 0
            for batch in self.post_office.fetch_X_GM_MSGID(self.batch_size):
                self.email_db.update_mail_queue(self.name, batch)
                log_progress(len(batch) + index, total, time.time())
                index += len(batch)

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
                            log_progress(index + 1, total, start_time)
                        index += 1

                    except Exception as e:
                        logging.error(f"Failed to fetch email with X-GM-MSGID '{email}': {e}")
                        continue

        logging.info("Shutting down classification thread! Waiting for other threads to finish.")
        self.ThreadSleep()

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
