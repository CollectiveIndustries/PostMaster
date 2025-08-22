import subprocess
import time  # Added for service restart delay


def is_clamd_running():
    """Check if the ClamAV service is running."""
    try:
        result = subprocess.run(["clamdscan", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        print("ClamAV is not installed or not found in the system path.")
        return False


def restart_clamd():
    """Restart the ClamAV service."""
    try:
        print("Restarting ClamAV service...")
        subprocess.run(["sudo", "systemctl", "restart", "clamd"], check=True)
        time.sleep(5)  # Give it a few seconds to restart
        if is_clamd_running():
            print("ClamAV service restarted successfully.")
        else:
            print("Failed to restart ClamAV service.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while restarting the ClamAV service: {e}")
