#!/usr/bin/env python3
"""
List all IMAP folders for debugging
Usage: python scripts/grabfolders.py [--config CONFIG_PATH] [--provider PROVIDER]
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config import config
from lib.config_manager import config_manager
from lib.post import PostOffice


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='List all available IMAP folders',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                              # List folders using default config
    %(prog)s --config /path/to/config.yaml
    %(prog)s --provider outlook           # Check Outlook folders
    %(prog)s --verbose                    # Show debug output
        """,
    )
    parser.add_argument(
        '--config', '-c', type=str, default=None, help='Path to configuration YAML file (default: from ConfigManager)'
    )
    parser.add_argument(
        '--provider',
        '-p',
        type=str,
        default='gmail',
        choices=['gmail', 'outlook'],
        help='Email provider to check (default: gmail)',
    )
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--save', '-s', type=str, help='Save folder list to file')
    return parser.parse_args()


def main():
    args = parse_args()

    # Initialize configuration
    try:
        config_manager.initialize(args.config)
        config._ensure_initialized()
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)

    # Create PostOffice instance
    post = PostOffice(args.provider, {'email': config.EMAIL_ADDRESS, 'password': config.PASSWORD})

    # Connect
    if args.verbose:
        print(f"Connecting to {args.provider}...")

    try:
        post.connect()
        if args.verbose:
            print("Connected successfully")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    # List folders
    if not hasattr(post.provider, 'imap_conn') or not post.provider.imap_conn:
        print("Error: Not connected to IMAP server")
        sys.exit(1)

    try:
        status, folders = post.provider.imap_conn.list()
        if status != 'OK':
            print(f"Failed to list folders: {status}")
            sys.exit(1)

        folder_list = []
        print('\nAvailable folders:')
        for folder in folders:
            folder_name = folder.decode().split('"/"')[-1].strip('"')
            folder_list.append(folder_name)
            print(f'  - {folder_name}')

        print(f"\nTotal: {len(folder_list)} folders")

        # Save to file if requested
        if args.save:
            with open(args.save, 'w') as f:
                for folder in folder_list:
                    f.write(f"{folder}\n")
            print(f"\nFolder list saved to: {args.save}")

    except Exception as e:
        print(f"Error listing folders: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
    finally:
        post.close()
        if args.verbose:
            print("\nConnection closed.")


if __name__ == "__main__":
    main()
