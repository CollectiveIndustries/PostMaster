import threading
import logging
import os
import time
import shutil
import gzip
from datetime import datetime
from .config import config

class LogRotation(threading.Thread):
    def __init__(self):
        """
        Thread to monitor and rotate log files when they exceed a given size.
        """
        super().__init__(name="LogRotationThread")
        self.daemon = True
        self.log_file = config.LOG_FILE
        self.backup_count = config.BACKUP_COUNT
        self.check_interval = config.CHECK_INTERVAL
        logging.info("Log rotation thread intilized.")

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
