#!/usr/bin/env python3
"""
Check queue status - diagnostic tool for PostMaster
Usage: python scripts/check_que.py [--config CONFIG_PATH]
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config import config
from lib.config_manager import config_manager
from lib.database import EmailDatabase


def main():
    # Parse arguments
    config_path = None
    if len(sys.argv) > 1 and sys.argv[1] == '--config':
        config_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Initialize configuration
    try:
        config_manager.initialize(config_path)
        config._ensure_initialized()
        print(f"✓ Configuration loaded")
        print(f"  Email: {getattr(config, 'EMAIL_ADDRESS', 'Not set')}")
        print(f"  Spam Learn: {getattr(config, 'SPAM_LEARN', 'Not set')}")
        print(f"  Ham Learn: {getattr(config, 'HAM_LEARN', 'Not set')}")
        print(f"  Training Data Path: {getattr(config, 'TRAINING_DATA_PATH', 'Not set')}")
        print()
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        sys.exit(1)

    db = EmailDatabase()

    # Check queue counts for each thread
    print("=" * 60)
    print("QUEUE STATUS")
    print("=" * 60)

    for marker in ['Trainer-Spam', 'Trainer-Ham', 'PostMan']:
        try:
            total = db.fetch_thread_marker_count(marker)
            print(f"{marker}: {total} pending")
        except Exception as e:
            print(f"{marker}: Error - {e}")

    # Direct query to see what's actually in the queue
    print("\n" + "=" * 60)
    print("DIRECT QUEUE QUERY")
    print("=" * 60)

    try:
        # Use raw query to avoid method issues
        result = db._safe_execute(
            "SELECT thread_marker, processed, COUNT(*) as cnt FROM mail_que GROUP BY thread_marker, processed;",
            fetch=True,
        )
        if result:
            print(f"{'Thread Marker':<20} {'Processed':<10} {'Count':<10}")
            print("-" * 40)
            for row in result:
                # Handle both tuple and dict results
                if isinstance(row, dict):
                    marker = row.get('thread_marker', 'Unknown')
                    processed = row.get('processed', '?')
                    count = row.get('cnt', 0)
                else:
                    marker = row[0] if len(row) > 0 else 'Unknown'
                    processed = row[1] if len(row) > 1 else '?'
                    count = row[2] if len(row) > 2 else 0
                print(f"{marker:<20} {processed:<10} {count:<10}")
        else:
            print("No entries found in mail_que")
    except Exception as e:
        print(f"Query error: {e}")

    # Check processed IDs
    print("\n" + "=" * 60)
    print("PROCESSED IDs")
    print("=" * 60)

    for marker in ['Trainer-Spam', 'Trainer-Ham', 'PostMan']:
        try:
            processed = db.get_processed_x_gm_msgids(marker)
            print(f"{marker}: {len(processed)} processed IDs")
            if len(processed) > 0 and len(processed) <= 10:
                print(f"  IDs: {list(processed)[:5]}...")
        except Exception as e:
            print(f"{marker}: Error - {e}")

    # Check model directory using config value
    print("\n" + "=" * 60)
    print("MODEL DIRECTORY")
    print("=" * 60)

    model_dir = getattr(config, 'TRAINING_DATA_PATH', None)
    if model_dir:
        print(f"Config path: {model_dir}")
        if os.path.exists(model_dir):
            files = os.listdir(model_dir)
            if files:
                print(f"Files in {model_dir}:")
                for f in files:
                    file_path = os.path.join(model_dir, f)
                    size = os.path.getsize(file_path)
                    print(f"  - {f} ({size} bytes)")
            else:
                print(f"{model_dir} is empty")
        else:
            print(f"{model_dir} does not exist")
            print("Creating directory...")
            try:
                os.makedirs(model_dir, exist_ok=True)
                print(f"✓ Created {model_dir}")
            except Exception as e:
                print(f"✗ Failed to create directory: {e}")
    else:
        print("TRAINING_DATA_PATH not set in config")

    # Also check the old path for comparison
    old_path = "/var/lib/spamvanquisher/data"
    if os.path.exists(old_path):
        print(f"\nOld path {old_path} exists with:")
        files = os.listdir(old_path)
        for f in files:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
