import logging
import os
import subprocess
import time
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def load_db_config(config_path: str | None = None) -> dict:
    """Load database configuration from the project YAML file."""
    if not config_path:
        config_path = Path(__file__).resolve().parent.parent / "config.d" / "config.yaml"
    else:
        config_path = Path(config_path)
        if not config_path.is_absolute():
            config_path = Path(__file__).resolve().parent.parent / config_path

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    db_cfg = cfg.get("database", {})
    return {
        "user": db_cfg.get("user", "root"),
        "password": db_cfg.get("password", ""),
        "host": db_cfg.get("host", "localhost"),
        "database": db_cfg.get("database", "postmaster_db"),
        "port": db_cfg.get("port", 3306),
    }


# pylint: disable=unused-argument
def run_cmd(cmd, db_user=None, db_pass=None, db_host=None, check=True, stdin_data=None):
    """Execute a command, optionally with DB credentials."""
    env = os.environ.copy()
    if db_pass:
        env["MYSQL_PWD"] = db_pass

    try:
        return subprocess.run(cmd, input=stdin_data, text=True, capture_output=True, check=check, env=env)
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr
        if db_pass and db_pass in stderr_msg:
            stderr_msg = stderr_msg.replace(db_pass, "********")
        if "incorrect password" in stderr_msg.lower() or "access denied" in stderr_msg.lower():
            logger.error("Authentication failed (database).")
        raise subprocess.CalledProcessError(e.returncode, e.cmd, output=e.stdout, stderr=stderr_msg) from e


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
            subprocess.run(["sudo"] + cmd, check=True, capture_output=True)
            logger.info("MariaDB started via: %s", " ".join(cmd))
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    logger.info("Falling back to mysqld_safe...")
    try:
        with subprocess.Popen(["sudo", "mysqld_safe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
            pass
        return True
    except Exception as e:
        logger.error("Failed to start MariaDB via mysqld_safe: %s", e)
        return False


def wait_for_mariadb(timeout: int = 30, db_user=None, db_pass=None, db_host=None) -> bool:
    """Poll until MariaDB accepts connections or timeout is reached."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            cmd = ["mysqladmin", "-u", db_user, "-h", db_host, "ping", "--silent"]
            run_cmd(cmd, db_user=db_user, db_pass=db_pass, db_host=db_host)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            time.sleep(1)
    return False


def provision_database(sql_path: str = "sql/install.sql", db_user=None, db_pass=None, db_host=None) -> bool:
    """Execute the SQL installation script to provision the database."""
    if not os.path.isabs(sql_path):
        base_dir = Path(__file__).resolve().parent.parent
        sql_file = base_dir / sql_path
    else:
        sql_file = Path(sql_path)

    if not sql_file.exists():
        logger.error("SQL installation script not found at: %s", sql_file)
        return False

    logger.info("Provisioning database using %s...", sql_file)
    try:
        with open(sql_file, "r", encoding="utf-8") as f:
            sql_content = f.read()
        cmd = ["mysql", "-u", db_user, "-h", db_host, "--default-character-set=utf8mb4"]
        run_cmd(cmd, db_user=db_user, db_pass=db_pass, db_host=db_host, stdin_data=sql_content)
        logger.info("Database provisioning completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Database provisioning failed: %s", e.stderr)
        return False


# pylint: disable=too-many-return-statements
def ensure_database_ready(config_path: str | None = None) -> bool:
    """
    Main entry point to ensure MariaDB is running and the application database is provisioned.
    Call this BEFORE importing `lib.config` to prevent OperationalError on startup.
    """
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")

    try:
        db_cfg = load_db_config(config_path)
    except FileNotFoundError as e:
        logger.error(str(e))
        return False
    except Exception as e:
        logger.error("Failed to load database configuration: %s", e)
        return False

    db_user = db_cfg["user"]
    db_pass = db_cfg["password"]
    db_name = db_cfg["database"]
    db_host = db_cfg["host"]

    logger.info("Checking MariaDB availability...")
    if not wait_for_mariadb(timeout=5, db_user=db_user, db_pass=db_pass, db_host=db_host):
        logger.warning("MariaDB is not responding. Attempting to start service...")
        if not start_mariadb_service():
            logger.error("Failed to start MariaDB automatically. Please start it manually.")
            return False

        if not wait_for_mariadb(timeout=30, db_user=db_user, db_pass=db_pass, db_host=db_host):
            logger.error("MariaDB failed to become ready within timeout.")
            return False

    logger.info("MariaDB is running. Checking database provisioning...")
    try:
        cmd = ["mysql", "-u", db_user, "-h", db_host, "-e", f"SHOW DATABASES LIKE '{db_name}';"]
        result = run_cmd(cmd, db_user=db_user, db_pass=db_pass, db_host=db_host)
        if db_name not in result.stdout:
            logger.info("Database '%s' not found. Running provisioning...", db_name)
            return provision_database(db_user=db_user, db_pass=db_pass, db_host=db_host)
        else:
            logger.info("Database '%s' already exists. Skipping provisioning.", db_name)
            return True
    except subprocess.CalledProcessError as e:
        logger.error("Failed to verify database existence: %s", e.stderr)
        return False
    except FileNotFoundError:
        logger.error("MySQL client tools not found. Please install mariadb-client or mysql-client.")
        return False
