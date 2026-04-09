import os
import subprocess
import sys
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def start_mariadb_service() -> bool:
    """Attempt to start the local MariaDB server using common service managers."""
    commands = [
        ["systemctl", "start", "mariadb"],
        ["systemctl", "start", "mysql"],
        ["service", "mariadb", "start"],
        ["service", "mysql", "start"],
    ]
    
    for cmd in commands:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"MariaDB started via: {' '.join(cmd)}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
            
    logger.info("Falling back to mysqld_safe...")
    try:
        subprocess.Popen(
            ["mysqld_safe"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception as e:
        logger.error(f"Failed to start MariaDB via mysqld_safe: {e}")
        return False

def wait_for_mariadb(timeout: int = 30) -> bool:
    """Poll until MariaDB accepts connections or timeout is reached."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            subprocess.run(
                ["mysqladmin", "ping", "--silent"], 
                check=True, 
                capture_output=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            time.sleep(1)
    return False

def provision_database(sql_path: str = "sql/install.sql") -> bool:
    """Execute the SQL installation script to provision the database."""
    if not os.path.isabs(sql_path):
        base_dir = Path(__file__).resolve().parent.parent
        sql_file = base_dir / sql_path
    else:
        sql_file = Path(sql_path)
        
    if not sql_file.exists():
        logger.error(f"SQL installation script not found at: {sql_file}")
        return False
        
    logger.info(f"Provisioning database using {sql_file}...")
    try:
        with open(sql_file, "r", encoding="utf-8") as f:
            subprocess.run(
                ["mysql", "--default-character-set=utf8mb4"], 
                stdin=f, 
                check=True, 
                capture_output=True
            )
        logger.info("Database provisioning completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace")
        logger.error(f"Database provisioning failed: {stderr}")
        return False

def ensure_database_ready() -> bool:
    """
    Main entry point to ensure MariaDB is running and the application database is provisioned.
    Call this BEFORE importing `lib.config` to prevent OperationalError on startup.
    """
    # Configure basic logging if not already configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

    logger.info("Checking MariaDB availability...")
    if not wait_for_mariadb(timeout=5):
        logger.warning("MariaDB is not responding. Attempting to start service...")
        if not start_mariadb_service():
            logger.error("Failed to start MariaDB automatically. Please start it manually.")
            return False
            
        if not wait_for_mariadb(timeout=30):
            logger.error("MariaDB failed to become ready within timeout.")
            return False
            
    logger.info("MariaDB is running. Checking database provisioning...")
    try:
        result = subprocess.run(
            ["mysql", "-e", "SHOW DATABASES LIKE 'SpamVanquisher';"],
            capture_output=True, text=True, check=True
        )
        if "SpamVanquisher" not in result.stdout:
            logger.info("Database 'SpamVanquisher' not found. Running provisioning...")
            return provision_database()
        else:
            logger.info("Database 'SpamVanquisher' already exists. Skipping provisioning.")
            return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to verify database existence: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        logger.error("MySQL client tools not found. Please install mariadb-client or mysql-client.")
        return False
