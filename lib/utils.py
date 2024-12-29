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
def save_failed_uids(uids_by_mailbox: dict):
    """
    Save the failed UIDs to a JSON file, keeping them separated by mailbox.

    Parameters:
    - uids_by_mailbox: A dictionary where keys are mailbox names, and values are sets of UIDs.
    """
    try:
        # Convert sets of UIDs back to lists for JSON serialization
        serializable_data = {
            mailbox: [uid.decode() if isinstance(uid, bytes) else str(uid)
                      for uid in uids]
            for mailbox, uids in uids_by_mailbox.items()
        }

        with open(config.FAILED_UID_FILE, "w") as file:
            json.dump(serializable_data, file, indent=4)

        logging.info(f"Saved failed UIDs for {len(uids_by_mailbox)} mailboxes.")
    except Exception as e:
        logging.error(f"Unexpected error saving failed UIDs: {e}", exc_info=True)

def load_failed_uids() -> dict:
    """
    Load the failed UIDs from a JSON file, keeping them separated by mailbox.

    Returns:
    - A dictionary where keys are mailbox names, and values are sets of UIDs.
    """
    try:
        with open(config.FAILED_UID_FILE, "r") as file:
            raw_data = json.load(file)
            
            # Convert UIDs to sets and ensure all UIDs are bytes
            uids_by_mailbox = {
                mailbox: set(
                    uid.encode() if isinstance(uid, str) else bytes(uid)
                    for uid in uids
                )
                for mailbox, uids in raw_data.items()
            }
        
        logging.info(f"Loaded failed UIDs for {len(uids_by_mailbox)} mailboxes.")
        return uids_by_mailbox

    except FileNotFoundError:
        logging.warning("Failed UIDs file not found. Starting with an empty structure.")
        return {}

    except json.JSONDecodeError as e:
        logging.error(f"Error parsing failed UIDs file: {e}", exc_info=True)
        return {}

    except Exception as e:
        logging.error(f"Unexpected error loading failed UIDs: {e}", exc_info=True)
        return {}
    
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