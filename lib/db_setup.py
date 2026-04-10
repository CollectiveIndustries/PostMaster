import logging
import os
import subprocess
import time
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


def run_cmd(cmd, db_user=None, db_pass=None, db_host=None, sudo_pass=None, check=True, stdin_data=None):
    """Execute a command, optionally with sudo and DB credentials."""
    needs_pass = False
    try:
        subprocess.run(["sudo", "-n", "true"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        needs_pass = True

    if needs_pass and sudo_pass:
        cmd = ["sudo", "-S"] + cmd
        input_data = f"{sudo_pass}\n"
        if stdin_data:
            input_data += stdin_data
    else:
        cmd = ["sudo"] + cmd if needs_pass else cmd
        input_data = stdin_data

    # Use MYSQL_PWD environment variable to avoid password leakage in process lists
    env = os.environ.copy()
    if db_pass:
        env["MYSQL_PWD"] = db_pass

    try:
        return subprocess.run(cmd, input=input_data, text=True, capture_output=True, check=check, env=env)
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr
        if sudo_pass and sudo_pass in stderr_msg:
            stderr_msg = stderr_msg.replace(sudo_pass, "********")
        if db_pass and db_pass in stderr_msg:
            stderr_msg = stderr_msg.replace(db_pass, "********")
        if "incorrect password" in stderr_msg.lower() or "access denied" in stderr_msg.lower():
            logger.error("Authentication failed (sudo or database).")
        raise subprocess.CalledProcessError(e.returncode, e.cmd, output=e.stdout, stderr=stderr_msg) from e


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
        subprocess.Popen(["mysqld_safe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        logger.error(f"Failed to start MariaDB via mysqld_safe: {e}")
        return False


def wait_for_mariadb(timeout: int = 30, db_user=None, db_pass=None, db_host=None, sudo_pass=None) -> bool:
    """Poll until MariaDB accepts connections or timeout is reached."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            cmd = ["mysqladmin", "-u", db_user, "-h", db_host, "ping", "--silent"]
            run_cmd(cmd, db_user=db_user, db_pass=db_pass, db_host=db_host, sudo_pass=sudo_pass)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            time.sleep(1)
    return False


def provision_database(
    sql_path: str = "sql/install.sql", db_user=None, db_pass=None, db_host=None, sudo_pass=None
) -> bool:
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
        cmd = ["mysql", "-u", db_user, "-h", db_host, "--default-character-set=utf8mb4"]
        run_cmd(cmd, db_user=db_user, db_pass=db_pass, db_host=db_host, sudo_pass=sudo_pass, stdin_data=sql_content)
        logger.info("Database provisioning completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Database provisioning failed: {e.stderr}")
        return False


def ensure_database_ready() -> bool:
    """
    Main entry point to ensure MariaDB is running and the application database is provisioned.
    Call this BEFORE importing `lib.config` to prevent OperationalError on startup.
    """
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

    env_vars = load_env()
    sudo_pass = env_vars.get("SUDO_PASS")
    db_user = env_vars.get("POSTMASTER_DB_USER")
    db_pass = env_vars.get("POSTMASTER_DB_PASSWORD")
    db_name = env_vars.get("POSTMASTER_DB_NAME")
    db_host = env_vars.get("POSTMASTER_DB_HOST", "localhost")

    if not all([db_user, db_pass, db_name]):
        logger.error(
            "Missing required database environment variables (POSTMASTER_DB_USER, POSTMASTER_DB_PASSWORD, POSTMASTER_DB_NAME)."
        )
        return False

    logger.info("Checking MariaDB availability...")
    if not wait_for_mariadb(timeout=5, db_user=db_user, db_pass=db_pass, db_host=db_host, sudo_pass=sudo_pass):
        logger.warning("MariaDB is not responding. Attempting to start service...")
        if not start_mariadb_service(sudo_pass=sudo_pass):
            logger.error("Failed to start MariaDB automatically. Please start it manually.")
            return False

        if not wait_for_mariadb(timeout=30, db_user=db_user, db_pass=db_pass, db_host=db_host, sudo_pass=sudo_pass):
            logger.error("MariaDB failed to become ready within timeout.")
            return False

    logger.info("MariaDB is running. Checking database provisioning...")
    try:
        cmd = ["mysql", "-u", db_user, "-h", db_host, "-e", f"SHOW DATABASES LIKE '{db_name}';"]
        result = run_cmd(cmd, db_user=db_user, db_pass=db_pass, db_host=db_host, sudo_pass=sudo_pass)
        if db_name not in result.stdout:
            logger.info(f"Database '{db_name}' not found. Running provisioning...")
            return provision_database(db_user=db_user, db_pass=db_pass, db_host=db_host, sudo_pass=sudo_pass)
        else:
            logger.info(f"Database '{db_name}' already exists. Skipping provisioning.")
            return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to verify database existence: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("MySQL client tools not found. Please install mariadb-client or mysql-client.")
        return False
