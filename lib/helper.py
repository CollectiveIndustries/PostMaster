from .config import config
import logging
import time

def extract_email_data(email: tuple):
    """
    Extracts data from the email based on configuration settings.
    """
    data = []
    if config.USE_SUBJECT:
        data.append(email[0])
    if config.USE_SENDER:
        data.append(email[1])
    if config.USE_RECIPIENT:
        data.append(email[2])
    if config.USE_BODY:
        data.append(email[3])
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

    # Format the timedelta into DD:HH:MM:SS
    days = etc // (24 * 3600)
    hours = (etc % (24 * 3600)) // 3600
    minutes = (etc % 3600) // 60
    seconds = etc % 60

    # Format the result
    formatted_etc = f"{days:02}:{hours:02}:{minutes:02}:{seconds:02}"
    logging.info(
        f"Processed {index}/{total} items "
        f"({index / total:.2%} complete). "
        f"Estimated time till completion: {formatted_etc}"
    )