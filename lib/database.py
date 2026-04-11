"""
This module provides the EmailDatabase class for interacting with a database
to manage email hashes, classifications, folders, mail queue, and processing logs.
"""

import logging
import threading
from typing import Dict, Generator, List, Optional

from CollectiveCore.MariaMod import MariaModule


class EmailDatabase:
    """
    Thin application-specific layer on top of MariaModule for email processing.
    """

    def __init__(self):
        self.db = MariaModule()
        self._db_lock = threading.Lock()
        self._closed = False

    def _ensure_connection(self):
        """Re-initialize database module if it was closed."""
        if self._closed:
            try:
                self.db = MariaModule()
                self._closed = False
                logging.debug("Re-initialized database connection.")
            except Exception as e:
                logging.error("Failed to re-initialize database connection: %s", e)

    def _safe_execute(self, query: str, params=None, fetch: bool = False, commit: bool = False):
        """Thread-safe wrapper for database execution with debug logging."""
        self._ensure_connection()
        with self._db_lock:
            try:
                logging.debug("DB Query: %s | Params: %s", query.strip().replace('\n', ' '), params)
                result = self.db.execute(query, params, fetch=fetch, commit=commit)
                if fetch and result:
                    logging.debug("DB Fetch Result: %s rows", len(result))
                return result
            except Exception as e:
                err_str = str(e)
                logging.error("MariaDB execute error: %s | Query: %s | Params: %s", e, query.strip(), params)
                # Attempt to reconnect on known connection errors
                if any(kw in err_str for kw in ["Lost connection", "Commands out of sync", "NoneType", "closed"]):
                    try:
                        self.db = MariaModule()
                        self._closed = False
                        logging.debug("Attempted DB reconnection after error.")
                    except Exception as re_err:
                        logging.error("DB reconnection failed: %s", re_err)
                raise

    def close(self) -> None:
        """Safely close the database connection if supported by the underlying module."""
        if self._closed:
            return
        self._closed = True
        try:
            if hasattr(self.db, 'close') and callable(self.db.close):
                self.db.close()
            elif hasattr(self.db, 'conn') and hasattr(self.db.conn, 'close'):
                self.db.conn.close()
        except Exception as e:
            logging.debug("Database connection close skipped or failed: %s", e)

    def check_and_reconnect(self) -> None:
        """Check database connection and reconnect if necessary."""
        self._ensure_connection()
        if hasattr(self.db, 'check_and_reconnect'):
            self.db.check_and_reconnect()
        elif hasattr(self.db, 'conn') and hasattr(self.db.conn, 'ping'):
            try:
                self.db.conn.ping(reconnect=True)
            except Exception:
                self.db = MariaModule()
                self._closed = False

    def add_email_hash(self, hash_id: str, x_gm_msgid: str, classification_id: str) -> None:
        logging.debug("Adding email hash: %s for msgid %s", hash_id, x_gm_msgid)
        query = """
            INSERT IGNORE INTO email_hashes (hash_id, x_gm_msgid, classification_id)
            VALUES (%s, %s, %s)
        """
        try:
            result = self._safe_execute(query, (hash_id, x_gm_msgid, classification_id), commit=True)
            logging.debug("DB insert affected %s rows", result.rowcount if hasattr(result, 'rowcount') else 'N/A')
        except Exception as e:
            logging.error("Failed to add email hash: %s", str(e))
            raise

    def get_classification(self, x_gm_msgid: str) -> Optional[str]:
        query = "SELECT classification_id FROM email_hashes WHERE x_gm_msgid = %s"
        result = self._safe_execute(query, (x_gm_msgid,), fetch=True)
        return result[0]["classification_id"] if result else None

    def get_mail_map(self) -> Optional[Dict[str, str]]:
        query = "SELECT classification_id, folder_name FROM classification_folders"
        result = self._safe_execute(query, fetch=True)
        return {row["classification_id"]: row["folder_name"] for row in result} if result else None

    # pylint: disable=too-many-positional-arguments
    def log_email_processing(
        self, sequence_number: str, hash_id: str, source_folder: str, destination_folder: str, status: str
    ) -> None:
        if not all([sequence_number, hash_id, source_folder, destination_folder, status]):
            raise ValueError("All arguments must be non-empty strings.")
        query = """
            INSERT INTO email_processing_log (sequence_number, hash_id, source_folder, destination_folder, status)
            VALUES (%s, %s, %s, %s, %s)
        """
        self._safe_execute(query, (sequence_number, hash_id, source_folder, destination_folder, status), commit=True)

    def add_folder_and_classification(self, classification_id: str, folder_name: str) -> None:
        try:
            # Avoid duplicate folder
            check_query = "SELECT 1 FROM classification_folders WHERE classification_id=%s AND folder_name=%s"
            if self._safe_execute(check_query, (classification_id, folder_name), fetch=True):
                logging.warning(
                    "Folder '%s' with classification ID '%s' already exists.", folder_name, classification_id
                )
                return

            # Ensure classification exists
            ensure_query = (
                "INSERT IGNORE INTO classifications (classification_id, description, is_dynamic) VALUES (%s, '', FALSE)"
            )
            self._safe_execute(ensure_query, (classification_id,), commit=True)

            # Add folder
            add_query = "INSERT INTO classification_folders (classification_id, folder_name) VALUES (%s, %s)"
            self._safe_execute(add_query, (classification_id, folder_name), commit=True)
        except Exception as e:
            logging.error("Failed to add folder/classification: %s", e)
            logging.warning("Ensure database schema is fully provisioned before starting threads.")

    def set_trained_flag(self, hash_ids: List[str], trained: bool = True) -> None:
        if not hash_ids:
            logging.warning("No hash IDs provided to set 'trained' flag.")
            return
        placeholders = ', '.join(['%s'] * len(hash_ids))
        query = f"UPDATE email_hashes SET trained=%s WHERE x_gm_msgid IN ({placeholders})"
        self._safe_execute(query, [trained, *hash_ids], commit=True)

    def is_trained(self, x_gm_msgid: str) -> bool:
        query = "SELECT trained FROM email_hashes WHERE x_gm_msgid = %s"
        result = self._safe_execute(query, (x_gm_msgid,), fetch=True)
        return result[0]["trained"] if result else False

    def update_mail_queue(self, thread_marker: str, msg_ids: List[int]) -> bool:
        if not msg_ids:
            logging.error("The input parameter msg_ids must be a non-empty list of integers.")
            return False

        query = """
            INSERT INTO mail_que (x_gm_msgid, thread_marker)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE added_at=CURRENT_TIMESTAMP
        """
        params = [(msg_id, thread_marker) for msg_id in msg_ids]
        try:
            # Use _safe_execute for each item to avoid cursor/connection state issues and rollback crashes
            for p in params:
                self._safe_execute(query, p, commit=True)
            return True
        except Exception as e:
            logging.error("Error updating mail queue: %s", e)
            return False

    def fetch_mail_from_queue(self, thread_marker: str, batch_size: int) -> Generator[str, None, None]:
        query = """
            SELECT x_gm_msgid
            FROM mail_que
            WHERE thread_marker=%s AND processed != -1
            LIMIT %s
        """
        result = self._safe_execute(query, (thread_marker, batch_size), fetch=True)
        x_gm_msgids = [row["x_gm_msgid"] for row in result]
        if x_gm_msgids:
            update_query = f"""
                UPDATE mail_que
                SET thread_marker=%s
                WHERE x_gm_msgid IN ({','.join(['%s']*len(x_gm_msgids))}) AND processed != -1
            """
            self._safe_execute(update_query, (thread_marker, *x_gm_msgids), commit=True)
            yield from x_gm_msgids

    def fetch_thread_marker_count(self, thread_marker: str) -> int:
        query = "SELECT COUNT(*) AS total_count FROM mail_que WHERE thread_marker=%s"
        result = self._safe_execute(query, (thread_marker,), fetch=True)
        return result[0]["total_count"] if result else 0

    def pop_from_que(self, msgid: int, thread_marker: str) -> bool:
        query = "DELETE FROM mail_que WHERE x_gm_msgid=%s AND thread_marker=%s"
        try:
            result = self._safe_execute(query, (msgid, thread_marker), commit=True)
            affected = getattr(result, 'rowcount', 0) if result else 0
            return affected > 0
        except Exception as e:
            logging.error("Error popping from queue: %s", e)
            return False
