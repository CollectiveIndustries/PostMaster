from __future__ import annotations  # Allows forward declarations
import json
import logging
import time
from .config import config
from .locks import failed_uid_lock

def extract_email_data(email: Email):
    """
    Extracts data from the email based on configuration settings.
    """
    data = []
    if config.USE_SUBJECT:
        data.append(email.subject)
    if config.USE_SENDER:
        data.append(email.sender)
    if config.USE_RECIPIENT:
        data.append(email.recipient)
    if config.USE_BODY:
        data.append(email.payload)
    return " ".join(data)

def log_progress(index, total, start_time):
    """
    Logs progress and estimated time to completion (ETC) for a loop.

    Args:
        index (int): The current iteration count (1-based index).
        total (int): The total number of iterations.
        start_time (float): The timestamp when the loop started.
    """
    elapsed_time = time.time() - start_time
    avg_time_per_item = elapsed_time / index if index > 0 else 0
    remaining_items = total - index
    etc = remaining_items * avg_time_per_item

    # Format the timedelta into days, hours, minutes, and seconds
    days = int(etc // (24 * 3600))
    hours = int((etc % (24 * 3600)) // 3600)
    minutes = int((etc % 3600) // 60)
    seconds = int(etc % 60)

    # Build the formatted output
    if days > 0:
        formatted_etc = f"{days} days, {hours:02}:{minutes:02}:{seconds:02}"
    else:
        formatted_etc = f"{hours:02}:{minutes:02}:{seconds:02}"

    # Log the progress and estimated time to completion
    logging.info(
        f"Processed {index}/{total} items "
        f"({index / total:.2%} complete). "
        f"Estimated time till completion: {formatted_etc}"
    )


# Utility methods for saving and loading failed UIDs
def save_failed_uids(uids: set):
    """Save the failed UIDs to a JSON file."""
    with failed_uid_lock:
        try:
            with open(config.FAILED_UID_FILE, "w") as file:
                # Convert UIDs to strings for JSON compatibility
                json.dump(
                    [uid.decode() if isinstance(uid, bytes) else uid for uid in uids], 
                    file
                )
            logging.info(f"Saved {len(uids)} failed UIDs.")
        except Exception as e:
            logging.error(f"Error saving failed UIDs: {e}", exc_info=True)

def load_failed_uids() -> set:
    """Load the failed UIDs from a JSON file."""
    try:
        with open(config.FAILED_UID_FILE, "r") as file:
            # Ensure UIDs are converted to bytes if necessary
            uids = set(
                uid.encode() if isinstance(uid, str) else uid for uid in json.load(file)
            )
        logging.info(f"Loaded {len(uids)} failed UIDs.")
        return uids
    except FileNotFoundError:
        logging.warning("Failed UIDs file not found. Starting with an empty set.")
        return set()
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing failed UIDs file: {e}", exc_info=True)
        return set()
    except Exception as e:
        logging.error(f"Unexpected error loading failed UIDs: {e}", exc_info=True)
        return set()
    
def interruptible_sleep(duration, stop_event):
    """Sleeps for the given duration in small intervals, allowing interruption."""
    interval = 0.1  # Check the stop_event every 0.1 seconds
    elapsed = 0

    while elapsed < duration:
        if stop_event.is_set():
            return
        time.sleep(interval)
        elapsed += interval

def ElapsedTimeFormat(start_time, stop_time) -> str:
    elapsed_time = stop_time - start_time  # Calculate the elapsed time
    elapsed_time_int = int(elapsed_time)  # Convert to integer (seconds only)
    
    # Calculate hours, minutes, seconds
    hours = elapsed_time_int // 3600
    minutes = (elapsed_time_int % 3600) // 60
    seconds = elapsed_time_int % 60
    
    # Format the time string, only including non-zero components
    if hours > 0:
        time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
    elif minutes > 0:
        time_str = f"{minutes:02}:{seconds:02}"
    else:
        time_str = f"{seconds:02}"
    return time_str