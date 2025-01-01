import MySQLdb
import logging

class EmailDatabase:
    def __init__(self, host: str, user: str, password: str, database: str, port: int = 3306):
        try:
            self.connection = MySQLdb.connect(host=host, user=user, passwd=password, db=database, port=port)
            self.cursor = self.connection.cursor()
            logging.info("Connected to the database successfully.")
            # save settings in case we need to reset the connection later
            self.host=host
            self.user=user
            self.password=password
            self.database=database
            self.port=port
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

    def add_email_hash(self, hash_id: str, x_gm_msgid: str, classification_id: str):
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

    def get_classification(self, x_gm_msgid):
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

    def get_folder_for_classification(self, classification_id: str):
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

    def log_email_processing(self, sequence_number: str, hash_id: str, source_folder: str, destination_folder: str, status: str):
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

    def add_folder_and_classification(self, classification_id: str, folder_name: str):
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

    def set_trained_flag(self, hash_id: str, trained: bool = True):
        """
        Updates the 'trained' flag for a given hash ID.

        Parameters:
        - hash_id: The SHA256 hash of the email.
        - trained: Boolean value to set the flag (default is True).
        """
        try:
            query = "UPDATE email_hashes SET trained = %s WHERE hash_id = %s"
            self.cursor.execute(query, (trained, hash_id))
            self.connection.commit()
            logging.debug(f"Set 'trained' flag to {trained} for hash ID: {hash_id}")
        except MySQLdb.Error as e:
            logging.error(f"Error setting 'trained' flag for hash ID {hash_id}: {e}")
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

    def update_mail_queue(self, msg_ids):
        # Ensure msg_ids is a list of integers
        if not isinstance(msg_ids, list) or not all(isinstance(i, int) for i in msg_ids):
            logging.error("The input parameter msg_ids must be a list of integers.")
            return False

        # Construct the insert SQL query for the list of msg_ids
        sql = (
            "INSERT INTO mail_que (x_gm_msgid) "
            "SELECT x_gm_msgid FROM (SELECT %s) AS new_ids "
            "WHERE new_ids.x_gm_msgid NOT IN (SELECT x_gm_msgid FROM mail_que);"
        )

        try:
            # Execute the query with the list of msg_ids as parameters
            self.cursor.executemany(sql, [(msg_id,) for msg_id in msg_ids])
            self.connection.commit()
            rows_affected = self.cursor.rowcount

            if rows_affected > 0:
                logging.debug(f"Successfully added {rows_affected} entries to mail_que.")
            else:
                logging.debug("No new entries added to mail_que. All records are up to date.")

            return True
        except MySQLdb.Error as e:
            logging.error(f"Error updating mail_que: {e}", exc_info=True)
            return False
        
    def fetch_from_que(self, limit):
        """Generator method to fetch `x_gm_msgid` from the mail_que table with a limit."""
        sql = (
            "SELECT x_gm_msgid FROM mail_que "
            "LIMIT %s"
        )

        try:
            self.cursor.execute(sql, (limit,))
            result = self.cursor.fetchall()
            for row in result:
                yield row[0]  # Yield each `x_gm_msgid`
        except MySQLdb.Error as e:
            logging.error(f"Error fetching from mail_que: {e}", exc_info=True)
            return []

    def pop_from_que(self, msg_id):
        """Method to pop a specific `x_gm_msgid` from the mail_que table."""
        sql = (
            "DELETE FROM mail_que WHERE x_gm_msgid = %s"
        )

        try:
            self.cursor.execute(sql, (msg_id,))
            self.connection.commit()
            rows_affected = self.cursor.rowcount

            if rows_affected > 0:
                logging.debug(f"Successfully removed x_gm_msgid {msg_id} from mail_que.")
            else:
                logging.debug(f"x_gm_msgid {msg_id} not found in mail_que.")
            
            return True
        except MySQLdb.Error as e:
            logging.error(f"Error popping from mail_que: {e}", exc_info=True)
            return False

# Example usage
# db = EmailDatabase(host="localhost", user="root", password="password", database="email_db")
# db.add_email_hash("somehash", "spam", ["ham", "promotion"])
# db.map_classification_to_folder("spam", "Spam")
# db.close()
