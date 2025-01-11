"""
This module provides the EmailDatabase class for interacting with a MySQL database
to manage email hashes, classifications, folders, and processing logs.
Classes:
    EmailDatabase: A class to handle database operations related to email processing.
Usage example:
    db = EmailDatabase()
    db.add_email_hash("somehash", "spam", "ham")
    db.close()
    A class to handle database operations related to email processing.
    Methods:
        __init__(): Initializes the database connection using configuration values.
        reconnect(): Re-establishes the database connection if it becomes stale.
        close(): Closes the database connection.
        add_email_hash(hash_id: str, x_gm_msgid: str, classification_id: str): Adds an email hash to the database.
        get_classification(x_gm_msgid: str): Retrieves the classification ID for a given email message ID.
        get_folder_for_classification(classification_id: str): Retrieves the folder name for a given classification ID.
        log_email_processing(sequence_number: str, hash_id: str, source_folder: str, destination_folder: str, status: str): Logs email processing details.
        add_folder_and_classification(classification_id: str, folder_name: str): Adds a folder and classification mapping to the database.
        set_trained_flag(hash_ids: list[int], trained: bool = True): Updates the 'trained' flag for a list of hash IDs.
        is_trained(x_gm_msgid: str) -> bool: Checks if the 'trained' flag is set for a given email message ID.
        update_mail_queue(msg_ids: list[int], thread_marker: str): Adds message IDs to the mail queue and marks them with the current thread's marker.
        fetch_mail_from_queue(thread_marker: str, batch_size: int): Fetches emails marked with a specific thread marker, yielding them one at a time.
        pop_from_que(msg_id: int, thread_marker: str): Removes an email from the queue after processing.
        fetch_thread_marker_count(thread_marker: str) -> int: Fetches the total count of emails for a specific thread marker.
"""
from typing import Generator, Optional, List, Dict
import MySQLdb
import MySQLdb.cursors
import logging
from .config import config

class EmailDatabase:
    def __init__(self):
        try:
            self.connection = MySQLdb.connect(
                host=config.SQL_HOST,
                user=config.SQL_USER,
                passwd=config.SQL_PASSWORD,
                db=config.SQL_DATABASE,
                port=config.SQL_PORT,
                cursorclass=MySQLdb.cursors.DictCursor,
            )
            self.cursor = self.connection.cursor()
            logging.info("Connected to the database successfully.")
        except MySQLdb.Error as e:
            logging.error(f"Error connecting to database: {e}")
            raise

    def check_and_reconnect(self):
        """Ensures the database connection is active; reconnects if necessary."""
        if not self.connection.open:
            self.reconnect()

    def reconnect(self):
        """
        Re-establish the database connection if it becomes stale.
        """
        try:
            logging.info("Reconnecting to MySQL database...")

            # Check if the connection is open before trying to close it
            if self.connection and self.connection.open:
                self.connection.close()
                logging.info("Closed stale connection.")

            # Establish a new connection
            self.connection = MySQLdb.connect(
                host=config.SQL_HOST,
                user=config.SQL_USER,
                passwd=config.SQL_PASSWORD,
                db=config.SQL_DATABASE,
                port=config.SQL_PORT,
                cursorclass=MySQLdb.cursors.DictCursor,
            )
            self.cursor = self.connection.cursor()
            logging.info("Reconnection successful.")
        except MySQLdb.Error as e:
            logging.error(f"Error reconnecting to the database: {e}")
            raise

    def close(self):
        """Closes the database connection."""
        try:
            self.cursor.close()
            self.connection.close()
            logging.info("Database connection closed.")
        except MySQLdb.Error as e:
            logging.error(f"Error closing database connection: {e}")

    def execute_query(self, query: str, params: tuple = None) -> list[dict]:
        """
        Execute a query and return the results as a list of dictionaries.
        """
        try:
            self.check_and_reconnect()
            self.cursor.execute(query, params or ())
            return self.cursor.fetchall()
        except MySQLdb.OperationalError as e:
            logging.error(f"OperationalError occurred: {e}")
            self.reconnect()
            self.cursor.execute(query, params or ())
            return self.cursor.fetchall()

    def execute_commit(self, query: str, params: Optional[tuple] = None):
        """Executes a query that modifies the database and commits changes."""
        self.check_and_reconnect()
        try:
            self.cursor.execute(query, params or ())
            self.connection.commit()
        except MySQLdb.Error as e:
            logging.error(f"Database operation failed: {e}")
            self.connection.rollback()
            raise

    def add_email_hash(self, hash_id: str, x_gm_msgid: str, classification_id: str) -> None:
        query = """
            INSERT IGNORE INTO email_hashes (hash_id, x_gm_msgid, classification_id)
            VALUES (%s, %s, %s)
        """
        self.execute_commit(query, (hash_id, x_gm_msgid, classification_id))

    def get_classification(self, x_gm_msgid: str) -> Optional[str]:
        query = "SELECT classification_id FROM email_hashes WHERE x_gm_msgid = %s"
        result = self.execute_query(query, (x_gm_msgid,))
        return result[0]["classification_id"] if result else None

    def get_mail_map(self) -> Optional[Dict[str, str]]:
        query = "SELECT classification_id, folder_name FROM classification_folders"
        result = self.execute_query(query)
        return {row["classification_id"]: row["folder_name"] for row in result} if result else None

    def log_email_processing(
        self, sequence_number: str, hash_id: str, source_folder: str, destination_folder: str, status: str
    ) -> None:
        if not all([sequence_number, hash_id, source_folder, destination_folder, status]):
            raise ValueError("All arguments must be non-empty strings.")

        insert_query = """
            INSERT INTO email_processing_log (sequence_number, hash_id, source_folder, destination_folder, status)
            VALUES (%s, %s, %s, %s, %s)
        """
        self.execute_commit(insert_query, (sequence_number, hash_id, source_folder, destination_folder, status))

    def add_folder_and_classification(self, classification_id: str, folder_name: str) -> None:
        check_folder_query = """
            SELECT 1 FROM classification_folders 
            WHERE classification_id = %s AND folder_name = %s
        """
        if self.execute_query(check_folder_query, (classification_id, folder_name)):
            logging.warning(f"Folder '{folder_name}' with classification ID '{classification_id}' already exists.")
            return

        ensure_classification_query = """
            INSERT IGNORE INTO classifications (classification_id, description, is_dynamic)
            VALUES (%s, '', FALSE)
        """
        self.execute_commit(ensure_classification_query, (classification_id,))

        add_folder_query = """
            INSERT INTO classification_folders (classification_id, folder_name)
            VALUES (%s, %s)
        """
        self.execute_commit(add_folder_query, (classification_id, folder_name))

    def set_trained_flag(self, hash_ids: List[str], trained: bool = True) -> None:
        if not hash_ids:
            logging.warning("No hash IDs provided to set 'trained' flag.")
            return

        placeholders = ', '.join(['%s'] * len(hash_ids))
        query = f"UPDATE email_hashes SET trained = %s WHERE x_gm_msgid IN ({placeholders})"
        self.execute_commit(query, [trained, *hash_ids])

    def is_trained(self, x_gm_msgid: str) -> bool:
        query = "SELECT trained FROM email_hashes WHERE x_gm_msgid = %s"
        result = self.execute_query(query, (x_gm_msgid,))
        return result[0]["trained"] if result else False

    def update_mail_queue(self, thread_marker: str, msg_ids: List[int]) -> bool:
        if not msg_ids:
            logging.error("The input parameter msg_ids must be a non-empty list of integers.")
            return False

        query = """
            INSERT INTO mail_que (x_gm_msgid, thread_marker)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE added_at = CURRENT_TIMESTAMP
        """
        params = [(msg_id, thread_marker) for msg_id in msg_ids]
        try:
            self.cursor.executemany(query, params)
            self.connection.commit()
            return True
        except MySQLdb.Error as e:
            logging.error(f"Error updating mail queue: {e}")
            self.connection.rollback()
            return False

    def fetch_mail_from_queue(self, thread_marker: str, batch_size: int) -> Generator[str, None, None]:
        query = """
            SELECT x_gm_msgid
            FROM mail_que
            WHERE thread_marker = %s AND processed != -1
            LIMIT %s
        """
        result = self.execute_query(query, (thread_marker, batch_size))
        x_gm_msgids = [row["x_gm_msgid"] for row in result]

        if x_gm_msgids:
            update_query = f"""
                UPDATE mail_que
                SET thread_marker = %s
                WHERE x_gm_msgid IN ({','.join(['%s'] * len(x_gm_msgids))})
                AND processed != -1
            """
            self.execute_commit(update_query, (thread_marker, *x_gm_msgids))
            yield from x_gm_msgids
    
    def fetch_thread_marker_count(self, thread_marker: str) -> int:
        """
        Fetch the total count of records associated with a specific thread_marker.
        """
        query = "SELECT COUNT(*) AS total_count FROM mail_que WHERE thread_marker = %s"
        result = self.execute_query(query, (thread_marker,))
        return result[0]['total_count'] if result else 0
