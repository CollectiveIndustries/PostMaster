import MySQLdb
import logging

class EmailDatabase:
    def __init__(self, host: str, user: str, password: str, database: str, port: int = 3306):
        try:
            self.connection = MySQLdb.connect(host=host, user=user, passwd=password, db=database, port=port)
            self.cursor = self.connection.cursor()
            logging.info("Connected to the database successfully.")
        except MySQLdb.Error as e:
            logging.error(f"Error connecting to database: {e}")
            raise

    def close(self):
        try:
            self.cursor.close()
            self.connection.close()
            logging.info("Database connection closed.")
        except MySQLdb.Error as e:
            logging.error(f"Error closing database connection: {e}")

    def add_email_hash(self, hash_id: str, classification_id: str, additional_classifications: list = None):
        try:
            additional_ids_json = None
            if additional_classifications:
                additional_ids_json = MySQLdb.escape_string(str(additional_classifications))
            query = """
                INSERT INTO email_hashes (hash_id, classification_id, additional_classification_ids)
                VALUES (%s, %s, %s)
            """
            self.cursor.execute(query, (hash_id, classification_id, additional_ids_json))
            self.connection.commit()
            logging.info(f"Inserted email hash {hash_id} with classification {classification_id}.")
        except MySQLdb.Error as e:
            logging.error(f"Error inserting email hash: {e}")
            self.connection.rollback()

    def get_classification(self, hash_id: str):
        try:
            query = "SELECT classification_id, additional_classification_ids FROM email_hashes WHERE hash_id = %s"
            self.cursor.execute(query, (hash_id,))
            result = self.cursor.fetchone()
            if result:
                classification_id, additional_ids = result
                logging.info(f"Retrieved classification for hash {hash_id}: {classification_id}, {additional_ids}")
                return classification_id, additional_ids
            else:
                logging.warning(f"No classification found for hash {hash_id}.")
                return None
        except MySQLdb.Error as e:
            logging.error(f"Error retrieving classification: {e}")
            return None

    def map_classification_to_folder(self, classification_id: str, folder_name: str):
        try:
            query = """
                INSERT INTO classification_folders (classification_id, folder_name)
                VALUES (%s, %s)
            """
            self.cursor.execute(query, (classification_id, folder_name))
            self.connection.commit()
            logging.info(f"Mapped classification {classification_id} to folder {folder_name}.")
        except MySQLdb.Error as e:
            logging.error(f"Error mapping classification to folder: {e}")
            self.connection.rollback()

    def get_folder_for_classification(self, classification_id: str):
        try:
            query = "SELECT folder_name FROM classification_folders WHERE classification_id = %s"
            self.cursor.execute(query, (classification_id,))
            result = self.cursor.fetchone()
            if result:
                folder_name = result[0]
                logging.info(f"Retrieved folder for classification {classification_id}: {folder_name}")
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
            logging.info(f"Logged email processing: {sequence_number}, {status}.")
        except MySQLdb.Error as e:
            logging.error(f"Error logging email processing: {e}")
            self.connection.rollback()
            
    def add_folder_and_classification(self, classification_id: str, folder_name: str):
        try:
            # Check if the classification_id exists in the classifications table
            self.cursor.execute("SELECT 1 FROM classifications WHERE classification_id = %s", (classification_id,))
            if self.cursor.fetchone() is None:
                # If no classification_id exists, insert the new classification_id
                logging.warning(f"Classification ID '{classification_id}' does not exist. Creating a new classification.")
    
                # Optionally, insert a default classification, or handle as needed
                # If you want to insert the classification as well (uncomment below)
                self.cursor.execute(
                    "INSERT INTO classifications (classification_id) VALUES (%s)", (classification_id,)
                )
                self.connection.commit()
    
            # Check if the folder_name with the given classification_id already exists
            self.cursor.execute(
                "SELECT 1 FROM classification_folders WHERE classification_id = %s AND folder_name = %s", 
                (classification_id, folder_name)
            )
            if self.cursor.fetchone() is not None:
                logging.info(f"Folder '{folder_name}' with classification ID '{classification_id}' already exists.")
                return  # Exit if the folder already exists
    
            # Insert the new folder and its classification mapping into classification_folders table
            self.cursor.execute(
                "INSERT INTO classification_folders (classification_id, folder_name) VALUES (%s, %s)",
                (classification_id, folder_name)
            )
            self.connection.commit()
            logging.info(f"Folder '{folder_name}' with classification ID '{classification_id}' added successfully.")
        
        except MySQLdb.Error as e:
            logging.error(f"Error adding folder and classification: {e}")
            self.connection.rollback()

# Example usage
# db = EmailDatabase(host="localhost", user="root", password="password", database="email_db")
# db.add_email_hash("somehash", "spam", ["ham", "promotion"])
# db.map_classification_to_folder("spam", "Spam")
# db.close()
