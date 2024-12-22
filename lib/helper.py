from .config import config

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