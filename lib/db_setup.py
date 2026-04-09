import os
import subprocess
import sys
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def load_env(env_path=".env"):
    """Load environment variables from a .env file."""
    env_vars = {}
    env_file = Path(env_path)
    if not env_file.is_absolute():
        env_file = Path(__file__).resolve().parent.parent / env_path
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars

def run_cmd(cmd, sudo_pass=None, check=True, stdin_data=None):
    """Execute a command, optionally with sudo using the provided password."""
    input_data = stdin_data
    if sudo_pass:
        cmd = ["sudo", "-S"] + cmd
        if input_data:
            input_data = f"{sudo_pass}\n{input_data}"
        else:
            input_data = f"{sudo_pass}\n"

    try:
        return subprocess.run(
            cmd,
            input=input_data,
            text=True,
            capture_output=True,
            check=check
        )
    except subprocess.CalledProcessError as e:
        if sudo_pass and "incorrect password" in e.stderr.lower():
            logger.error("Sudo password incorrect.")
        raise

def start_mariadb_service(sudo_pass=None) -> bool:
    """Attempt to start the local MariaDB server using common service managers."""
    commands = [
        ["systemctl", "start", "mariadb"],
        ["systemctl", "start", "mysql"],
        ["service", "mariadb", "start"],
        ["service", "mysql", "start"],
    ]
    
    for cmd in commands:
        try:
            run_cmd(cmd, sudo_pass=sudo_pass)
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

def wait_for_mariadb(timeout: int = 30, sudo_pass=None) -> bool:
    """Poll until MariaDB accepts connections or timeout is reached."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            run_cmd(["mysqladmin", "-u", "root", "ping", "--silent"], sudo_pass=sudo_pass)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            time.sleep(1)
    return False

def provision_database(sql_path: str = "sql/install.sql", sudo_pass=None) -> bool:
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
            sql_content = f.read()
        run_cmd(
            ["mysql", "-u", "root", "--default-character-set=utf8mb4"], 
            sudo_pass=sudo_pass,
            stdin_data=sql_content
        )
        logger.info("Database provisioning completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        # Since text=True is used in run_cmd, e.stderr is already a string
        logger.error(f"Database provisioning failed: {e.stderr}")
        return False

def ensure_database_ready() -> bool:
    """
    Main entry point to ensure MariaDB is running and the application database is provisioned.
    Call this BEFORE importing `lib.config` to prevent OperationalError on startup.
    """
    # Configure basic logging if not already configured
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

    # Load sudo password from .env
    env_vars = load_env()
    sudo_pass = env_vars.get("SUDO_PASS")

    logger.info("Checking MariaDB availability...")
    if not wait_for_mariadb(timeout=5, sudo_pass=sudo_pass):
        logger.warning("MariaDB is not responding. Attempting to start service...")
        if not start_mariadb_service(sudo_pass=sudo_pass):
            logger.error("Failed to start MariaDB automatically. Please start it manually.")
            return False
            
        if not wait_for_mariadb(timeout=30, sudo_pass=sudo_pass):
            logger.error("MariaDB failed to become ready within timeout.")
            return False
            
    logger.info("MariaDB is running. Checking database provisioning...")
    try:
        result = run_cmd(
            ["mysql", "-u", "root", "-e", "SHOW DATABASES LIKE 'SpamVanquisher';"],
            sudo_pass=sudo_pass
        )
        if "SpamVanquisher" not in result.stdout:
            logger.info("Database 'SpamVanquisher' not found. Running provisioning...")
            return provision_database(sudo_pass=sudo_pass)
        else:
            logger.info("Database 'SpamVanquisher' already exists. Skipping provisioning.")
            return True
    except subprocess.CalledProcessError as e:
        # Since text=True is used in run_cmd, e.stderr is already a string
        logger.error(f"Failed to verify database existence: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("MySQL client tools not found. Please install mariadb-client or mysql-client.")
        return False
