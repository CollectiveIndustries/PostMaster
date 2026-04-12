# save as debug_config_manager.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from lib.config_manager import config_manager

# Initialize with your config
config_manager.initialize('/opt/config.d/config.yaml')

# Print ALL sections to see what's loaded
print("=" * 60)
print("ALL CONFIGURATION SECTIONS")
print("=" * 60)

# Get the raw config
raw_config = config_manager.get_all()
for section, values in raw_config.items():
    print(f"\nSection: {section}")
    if isinstance(values, dict):
        for key, value in values.items():
            if 'password' in key.lower():
                value = '********'
            print(f"  {key}: {value}")
    else:
        print(f"  {values}")

print("\n" + "=" * 60)
print("DAEMONSETTINGS SECTION SPECIFICALLY")
print("=" * 60)
daemon = config_manager.get_section('DaemonSettings')
print(f"DaemonSettings: {daemon}")
print(f"data_path: {daemon.get('data_path') if daemon else 'NOT FOUND'}")
