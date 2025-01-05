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
from typing import Generator, Optional
import MySQLdb
import logging
from .config import config

class EmailDatabase:
    def __init__(self):
        try:
            # Fetch values from the config.VALUE object
            self.host = config.SQL_HOST
            self.user = config.SQL_USER
            self.password = config.SQL_PASSWORD
            self.database = config.SQL_DATABASE
            self.port = config.SQL_PORT

            # Establish the connection to the database
            self.connection = MySQLdb.connect(
                host=self.host, user=self.user, passwd=self.password, 
                db=self.database, port=self.port
            )
            self.cursor = self.connection.cursor()
            logging.info("Connected to the database successfully.")

        except MySQLdb.Error as e:
            logging.error(f"Error connecting to database: {e}")
            raise

    def reconnect(self):
        """
        Re-establish the database connection if it becomes stale.
        """
        try:
            logging.info("Reconnecting to MySQL database...")
            self.connection.close()
        except Exception:
            pass  # Ignore errors when closing
        finally:
            self.connection = MySQLdb.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
            )
            self.cursor = self.connection.cursor()
            logging.info("Reconnection successful.")

    def close(self):
        try:
            self.cursor.close()
            self.connection.close()
            logging.info("Database connection closed.")
        except MySQLdb.Error as e:
            logging.error(f"Error closing database connection: {e}")

    def add_email_hash(self, hash_id: str, x_gm_msgid: str, classification_id: str) -> None:
        """
        Adds an email hash to the database.

        This method inserts a new record into the email_hashes table with the provided
        hash_id, x_gm_msgid, and classification_id. If the insertion is successful, the
        transaction is committed. If an error occurs, the transaction is rolled back and
        an error message is logged.

        Args:
            hash_id (str): The hash ID of the email.
            x_gm_msgid (str): The Gmail message ID of the email.
            classification_id (str): The classification ID of the email.

        Raises:
            MySQLdb.Error: If an error occurs during the database operation.
        """
        try:
            query = """
                INSERT IGNORE INTO email_hashes (hash_id, x_gm_msgid, classification_id)
                VALUES (%s, %s, %s)
            """
            self.cursor.execute(query, (hash_id, x_gm_msgid, classification_id))
            self.connection.commit()
            logging.debug(f"Inserted email hash {hash_id} with classification {classification_id}.")
        except MySQLdb.Error as e:
            logging.error(f"Error inserting email hash: {e}")
            self.connection.rollback()

    def get_classification(self, x_gm_msgid: str) -> str:
        """
        Retrieves the classification ID for a given email message ID.

        Args:
            x_gm_msgid (str): The Gmail message ID of the email.

        Returns:
            str: The classification ID of the email.

        Raises:
            MySQLdb.OperationalError: If unable to fetch classification after retries.
        """
        max_retries = 5  # Set a limit on the number of retries
        retries = 0
        while retries < max_retries:
            try:
                query = "SELECT classification_id FROM email_hashes WHERE x_gm_msgid = %s"
                self.cursor.execute(query, (x_gm_msgid,))
                return self.cursor.fetchone()
            except MySQLdb.OperationalError as e:
                logging.warning(f"MySQL connection lost: {e}. Attempting to reconnect (attempt {retries + 1} of {max_retries}).")
                self.reconnect()
                retries += 1
        # If we exhaust retries, raise an exception
        raise MySQLdb.OperationalError(f"Unable to fetch classification after {max_retries} retries.")

    def get_folder_for_classification(self, classification_id: str) -> Optional[str]:
        """
        Retrieve the folder name associated with a given classification ID.
        Args:
            classification_id (str): The ID of the classification to retrieve the folder for.
        Returns:
            Optional[str]: The name of the folder associated with the classification ID,
                           or None if no folder is found or an error occurs.
        """
        try:
            query = "SELECT folder_name FROM classification_folders WHERE classification_id = %s"
            self.cursor.execute(query, (classification_id,))
            result = self.cursor.fetchone()
            if result:
                folder_name = result[0]
                logging.debug(f"Retrieved folder for classification {classification_id}: {folder_name}")
                return folder_name
            else:
                logging.warning(f"No folder found for classification {classification_id}.")
                return None
        except MySQLdb.Error as e:
            logging.error(f"Error retrieving folder for classification: {e}")
            return None

    def log_email_processing(self, sequence_number: str, hash_id: str, source_folder: str, destination_folder: str, status: str) -> None:
        """
        Logs email processing details.

        This method inserts a new record into the email_processing_log table with the provided
        sequence_number, hash_id, source_folder, destination_folder, and status. If the insertion
        is successful, the transaction is committed. If an error occurs, the transaction is rolled
        back and an error message is logged.

        Args:
            sequence_number (str): The sequence number of the email processing event.
            hash_id (str): The hash ID of the email.
            source_folder (str): The source folder of the email.
            destination_folder (str): The destination folder of the email.
            status (str): The status of the email processing event.

        Raises:
            MySQLdb.Error: If an error occurs during the database operation.
        """
        try:
            query = """
                INSERT INTO email_processing_log (sequence_number, hash_id, source_folder, destination_folder, status)
                VALUES (%s, %s, %s, %s, %s)
            """
            self.cursor.execute(query, (sequence_number, hash_id, source_folder, destination_folder, status))
            self.connection.commit()
            logging.debug(f"Logged email processing: {sequence_number}, {status}.")
        except MySQLdb.Error as e:
            logging.error(f"Error logging email processing: {e}")
            self.connection.rollback()

    def add_folder_and_classification(self, classification_id: str, folder_name: str) -> None:
        """
        Adds a folder and classification mapping to the database.

        This method ensures that the folder_name exists in the classification_folders table
        for the given classification_id. If the folder already exists, a warning is logged.
        If the classification_id does not exist in the classifications table, it is added.
        Finally, the folder-classification mapping is inserted into the classification_folders table.

        Args:
            classification_id (str): The ID of the classification.
            folder_name (str): The name of the folder to map to the classification.

        Raises:
            MySQLdb.Error: If an error occurs during the database operation.
        """
        try:
            # Ensure the folder_name exists in the classification_folders table for the classification_id
            check_folder_query = """
                SELECT 1 FROM classification_folders 
                WHERE classification_id = %s AND folder_name = %s
            """
            self.cursor.execute(check_folder_query, (classification_id, folder_name))
            if self.cursor.fetchone():
                logging.warning(f"Folder '{folder_name}' with classification ID '{classification_id}' already exists.")
                return  # Exit if the folder already exists

            # Ensure the classification_id exists in the classifications table
            ensure_classification_query = """
                INSERT IGNORE INTO classifications (classification_id, description, is_dynamic)
                VALUES (%s, '', FALSE)
            """
            self.cursor.execute(ensure_classification_query, (classification_id,))
            self.connection.commit()  # Commit to ensure classification_id is added if missing

            # Insert the folder-classification mapping into classification_folders
            add_folder_query = """
                INSERT INTO classification_folders (classification_id, folder_name)
                VALUES (%s, %s)
            """
            self.cursor.execute(add_folder_query, (classification_id, folder_name))
            self.connection.commit()
            logging.info(f"Successfully added folder '{folder_name}' with classification ID '{classification_id}'.")

        except MySQLdb.Error as e:
            logging.error(f"Error adding folder and classification: {e}")
            self.connection.rollback()

    def set_trained_flag(self, hash_ids: list[str], trained: bool = True) -> None:
        """
        Updates the 'trained' flag for a list of hash IDs.
    
        Parameters:
        - hash_ids: List of hash IDs (integers).
        - trained: Boolean value to set the flag (default is True).
        """
        try:
            # Ensure hash_ids is not empty
            if not hash_ids:
                logging.warning("No hash IDs provided to set 'trained' flag.")
                return
            
            # Create placeholders for the query
            placeholders = ', '.join(['%s'] * len(hash_ids))
            query = f"UPDATE email_hashes SET trained = %s WHERE hash_id IN ({placeholders})"
            
            # Execute the query with all hash_ids
            self.cursor.execute(query, [trained, *hash_ids])
            self.connection.commit()
            logging.debug(f"Set 'trained' flag to {trained} for hash IDs: {hash_ids}")
        except MySQLdb.Error as e:
            logging.error(f"Error setting 'trained' flag for hash IDs {hash_ids}: {e}")
            self.connection.rollback()


    def is_trained(self, x_gm_msgid: str) -> bool:
        """
        Checks if the 'trained' flag is set for a given hash ID.
        
        Parameters:
        - x_gm_msgid: The x_gm_msgid of the email.
        
        Returns:
        - Boolean indicating if the email has been trained.
        """
        try:
            query = "SELECT trained FROM email_hashes WHERE x_gm_msgid = %s"
            self.cursor.execute(query, (x_gm_msgid,))
            result = self.cursor.fetchone()
            if result:
                trained_flag = result[0]
                logging.debug(f"Retrieved 'trained' flag for hash ID {x_gm_msgid}: {trained_flag}")
                return trained_flag
            else:
                return False
        except MySQLdb.Error as e:
            logging.error(f"Error checking 'trained' flag for hash ID {x_gm_msgid}: {e}")
            return False

    def update_mail_queue(self, msg_ids: list[int], thread_marker: str):
        """Add msg_ids to the queue and mark them with the current thread's marker."""
        # Ensure msg_ids is a list of integers
        if not isinstance(msg_ids, list) or not all(isinstance(i, int) for i in msg_ids):
            logging.error("The input parameter msg_ids must be a list of integers.")
            return False

        sql = (
            "INSERT INTO mail_que (x_gm_msgid, thread_marker) "
            "VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE added_at = CURRENT_TIMESTAMP"
            )

        try:
            # Execute the query with the list of msg_ids and the current thread's marker
            params = [(msg_id, thread_marker) for msg_id in msg_ids]
            self.cursor.executemany(sql, params)
            self.connection.commit()
            rows_affected = self.cursor.rowcount

            if rows_affected > 0:
                logging.debug(f"Successfully added or updated {rows_affected} entries in mail_que.")
            else:
                logging.debug("No new entries added to mail_que. All records are up to date.")

            return True
        except MySQLdb.Error as e:
            logging.error(f"Error updating mail_que: {e}", exc_info=True)
            return False

    def fetch_mail_from_queue(self, thread_marker: str, batch_size: int) -> Generator[str, None, None]:
        """
        Fetches email IDs from the mail queue in batches and marks them with the current thread's marker.
        Args:
            thread_marker (str): The marker used to identify the current thread.
            batch_size (int): The number of email IDs to fetch in each batch.
        Yields:
            str: The email ID from the mail queue.
        Raises:
            MySQLdb.Error: If there is an error fetching emails from the queue.
        """
        try:
            # Fetch email IDs in batches
            query = f"SELECT x_gm_msgid FROM mail_que WHERE thread_marker = %s LIMIT %s"
            self.cursor.execute(query, (thread_marker, batch_size))
            result = self.cursor.fetchall()
    
            # Collect the email IDs
            x_gm_msgids = [row[0] for row in result]
    
            if x_gm_msgids:
                # Mark emails with the current thread's marker while fetching them
                update_query = f"UPDATE mail_que SET thread_marker = %s WHERE x_gm_msgid IN ({','.join(['%s'] * len(x_gm_msgids))})"
                self.cursor.execute(update_query, (thread_marker, *x_gm_msgids))
                self.connection.commit()
    
                # Yield email IDs one by one
                for x_gm_msgid in x_gm_msgids:
                    yield x_gm_msgid
            else:
                logging.debug("No emails found for the specified thread_marker.")
    
        except MySQLdb.Error as e:
            logging.error(f"Error fetching emails from queue: {e}")

    def pop_from_que(self, msg_id: int, thread_marker: str) -> bool:
        """
        Removes an email from the queue after processing.

        This method deletes a record from the mail_que table with the provided
        msg_id and thread_marker. If the deletion is successful, the transaction
        is committed. If an error occurs, the transaction is rolled back and an
        error message is logged.

        Args:
            msg_id (int): The message ID of the email to be removed.
            thread_marker (str): The thread marker associated with the email.

        Returns:
            bool: True if the email was successfully removed, False otherwise.

        Raises:
            MySQLdb.Error: If an error occurs during the database operation.
        """
        try:
            # Ensure only the current thread can pop its own emails
            query = "DELETE FROM mail_que WHERE x_gm_msgid = %s AND thread_marker = %s"
            self.cursor.execute(query, (msg_id, thread_marker))
            self.connection.commit()

            rows_affected = self.cursor.rowcount
            if rows_affected > 0:
                logging.debug(f"Successfully removed x_gm_msgid {msg_id} from mail_que.")
            else:
                logging.debug(f"x_gm_msgid {msg_id} not found or being processed by another thread.")

            return True
        except MySQLdb.Error as e:
            logging.error(f"Error popping from mail_que: {e}", exc_info=True)
            return False
        
    def fetch_thread_marker_count(self, thread_marker: str) -> int:
        """
        Fetch the total count of emails for a specific thread_marker.
        
        Args:
            thread_marker (str): The thread_marker to filter by.

        Returns:
            int: The total count of emails for the given thread_marker.
        """
        try:
            query = """
                SELECT 
                    COALESCE(thread_marker, 'Total') AS thread_marker,
                    COUNT(*) AS count
                FROM 
                    SpamVanquisher.mail_que
                WHERE 
                    thread_marker = %s;
            """
            self.cursor.execute(query, (thread_marker,))
            result = self.cursor.fetchone()
            
            if result:
                return result[1]  # The `count` column
            else:
                return 0  # No rows found
        except MySQLdb.Error as e:
            logging.error(f"Error fetching thread marker count: {e}", exc_info=True)
            return 0
        finally:
            self.connection.commit()
