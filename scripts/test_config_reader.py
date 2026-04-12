# save as test_config_reader.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from lib.config_manager import config_manager

config_manager.initialize('/opt/config.d/config.yaml')

daemon = config_manager.get_section('DaemonSettings')
print(f"DaemonSettings section: {daemon}")
print(f"data_path value: {daemon.get('data_path') if daemon else 'NOT FOUND'}")
