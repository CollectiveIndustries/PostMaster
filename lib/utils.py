from __future__ import annotations  # Allows forward declarations

import logging
import re
import time

from .config import config

def normalize_email(email: str) -> str:
    """
    Normalizes an email address by converting it to lowercase and removing any extra whitespace.

    Args:
        email (str): The email address to be normalized.

    Returns:
        str: The normalized email address.
    """
    return email.lower().strip()

def log_progress(index, total, start_time, stage="Processing"):
    # ... rest of the code ...

def interruptible_sleep(duration, stop_event):
    """
    An interruptible sleep function that can be stopped by a provided event.

    Args:
        duration (float): The duration for which to sleep in seconds.
        stop_event (threading.Event): An event that can be set to stop the sleep.
    """
    start_time = time.time()
    elapsed_time = 0
    while elapsed_time < duration and not stop_event.wait(1):
        elapsed_time += 1

def sort_emails_by_folder(all_mail: list[Email], classification_map: dict) -> dict:
    # ... rest of the code ...

def normalize_emails(emails: list[str]) -> list[str]:
    """
    Normalizes a list of email addresses by converting each one to lowercase and removing any extra whitespace.

    Args:
        emails (list): A list of email addresses to be normalized.

    Returns:
        list: The normalized list of email addresses.
    """
    return [normalize_email(email) for email in emails]
