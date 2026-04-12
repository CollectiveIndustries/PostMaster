#!/usr/bin/env python3
"""
Debug tool for testing PostOffice IMAP connections
Usage: python scripts/debug_postoffice.py [--config CONFIG_PATH] [--verbose]
"""

import argparse
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config_manager import config_manager
from lib.config import config
from lib.post import PostOffice


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s:%(message)s'
    )


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Debug PostOffice IMAP connections',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                          # Use default config path
    %(prog)s --config /path/to/config.yaml
    %(prog)s --verbose                # Enable debug logging
    %(prog)s --list-folders           # List all available IMAP folders
    %(prog)s --test-folder INBOX      # Test specific folder access
        """
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to configuration YAML file (default: from ConfigManager)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose debug output'
    )
    parser.add_argument(
        '--list-folders', '-l',
        action='store_true',
        help='List all available IMAP folders'
    )
    parser.add_argument(
        '--test-folder', '-t',
        type=str,
        help='Test access to a specific folder (e.g., INBOX, SPAM)'
    )
    parser.add_argument(
        '--provider', '-p',
        type=str,
        default='gmail',
        choices=['gmail', 'outlook'],
        help='Email provider to test (default: gmail)'
    )
    return parser.parse_args()


def list_folders(post: PostOffice) -> None:
    """List all available IMAP folders"""
    if not hasattr(post.provider, 'imap_conn') or not post.provider.imap_conn:
        print("Error: Not connected. Run with --verbose to see connection issues.")
        return
    
    try:
        status, folders = post.provider.imap_conn.list()
        if status == 'OK':
            print("\nAvailable folders:")
            for folder in folders:
                # Decode and clean up folder name
                folder_name = folder.decode().split('"/"')[-1].strip('"')
                print(f"  - {folder_name}")
        else:
            print(f"Failed to list folders: {status}")
    except Exception as e:
        print(f"Error listing folders: {e}")


def test_folder(post: PostOffice, folder: str) -> None:
    """Test access to a specific folder"""
    if not hasattr(post.provider, 'imap_conn') or not post.provider.imap_conn:
        print("Error: Not connected. Run with --verbose to see connection issues.")
        return
    
    try:
        status, count = post.provider.imap_conn.select(folder, readonly=True)
        if status == 'OK':
            msg_count = count[0].decode() if count else '0'
            print(f"\nFolder '{folder}': OK - {msg_count} messages")
            
            # Try to search for messages
            status, data = post.provider.imap_conn.search(None, 'ALL')
            if status == 'OK':
                msg_ids = data[0].split()
                print(f"  Total messages: {len(msg_ids)}")
                if len(msg_ids) > 0:
                    print(f"  First 5 message IDs: {msg_ids[:5]}")
        else:
            print(f"Folder '{folder}': Failed to select - {status}")
    except Exception as e:
        print(f"Error testing folder '{folder}': {e}")


def main():
    args = parse_args()
    setup_logging(args.verbose)
    
    # Initialize configuration
    try:
        config_manager.initialize(args.config)
        config._ensure_initialized()
        print(f"Configuration loaded successfully")
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)
    
    # Display config info (redacted)
    print(f"\nEmail: {config.EMAIL_ADDRESS}")
    print(f"Password length: {len(config.PASSWORD)}")
    print(f"IMAP Server: {config.IMAP_URL}:{config.IMAP_PORT}")
    print()
    
    # Create PostOffice instance
    post = PostOffice(args.provider, {
        'email': config.EMAIL_ADDRESS,
        'password': config.PASSWORD
    })
    
    # Check internal state before connection
    print(f"PostOffice type: {type(post)}")
    print(f"Provider type: {type(post.provider)}")
    print(f"Has imap_conn? {hasattr(post.provider, 'imap_conn')}")
    print()
    
    # Connect
    print("Connecting...")
    try:
        post.connect()
        print("✓ Connection successful")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    
    # Show connection state
    print(f"\nAfter connect - imap_conn: {getattr(post.provider, 'imap_conn', 'NOT SET')}")
    
    # List folders if requested
    if args.list_folders:
        list_folders(post)
    
    # Test specific folder if requested
    if args.test_folder:
        test_folder(post, args.test_folder)
    
    # If no specific action, test INBOX
    if not args.list_folders and not args.test_folder:
        test_folder(post, 'INBOX')
    
    # Cleanup
    post.close()
    print("\nConnection closed.")


if __name__ == "__main__":
    main()