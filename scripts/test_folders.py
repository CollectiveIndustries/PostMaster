#!/usr/bin/env python3
"""
Test IMAP folder access and count messages in specified folders
Usage: python scripts/test_folders.py [--config CONFIG_PATH] [--folders FOLDER1 FOLDER2 ...] [--list-all]
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config_manager import config_manager
from lib.config import config
from lib.post import PostOffice


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Test IMAP folder access and count messages',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                                    # Test default folders from config
    %(prog)s --folders INBOX "INBOX/Spam"       # Test specific folders
    %(prog)s --list-all                         # List all available folders first
    %(prog)s --config /opt/config.d/config.yaml
    %(prog)s --provider outlook                 # Test Outlook instead of Gmail
    %(prog)s --verbose                          # Show debug output
        """
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to configuration YAML file (default: from ConfigManager)'
    )
    parser.add_argument(
        '--provider', '-p',
        type=str,
        default='gmail',
        choices=['gmail', 'outlook'],
        help='Email provider to test (default: gmail)'
    )
    parser.add_argument(
        '--folders', '-f',
        nargs='+',
        help='List of folders to test (space-separated)'
    )
    parser.add_argument(
        '--list-all', '-l',
        action='store_true',
        help='List all available folders before testing'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    return parser.parse_args()


def list_all_folders(post: PostOffice) -> list:
    """List all available IMAP folders and return their names"""
    if not hasattr(post.provider, 'imap_conn') or not post.provider.imap_conn:
        print("Error: Not connected to IMAP server")
        return []
    
    try:
        status, folders = post.provider.imap_conn.list()
        if status != 'OK':
            print(f"Failed to list folders: {status}")
            return []
        
        folder_list = []
        print("\n" + "="*60)
        print("Available folders:")
        print("="*60)
        for folder in folders:
            folder_name = folder.decode().split('"/"')[-1].strip('"')
            folder_list.append(folder_name)
            print(f"  - {folder_name}")
        print(f"\nTotal: {len(folder_list)} folders")
        print("="*60)
        return folder_list
    except Exception as e:
        print(f"Error listing folders: {e}")
        return []


def test_folder(post: PostOffice, folder: str) -> dict:
    """Test a single folder and return status and message count"""
    result = {'folder': folder, 'status': 'UNKNOWN', 'count': 0, 'error': None}
    
    if not hasattr(post.provider, 'imap_conn') or not post.provider.imap_conn:
        result['status'] = 'ERROR'
        result['error'] = 'Not connected'
        return result
    
    try:
        status, data = post.provider.imap_conn.select(folder, readonly=True)
        if status == 'OK':
            result['status'] = 'OK'
            # Get message count
            status, msg_ids = post.provider.imap_conn.search(None, 'ALL')
            if status == 'OK':
                result['count'] = len(msg_ids[0].split()) if msg_ids[0] else 0
            else:
                result['error'] = f"Search failed: {status}"
        else:
            result['status'] = 'FAILED'
            result['error'] = f"Select failed: {data}"
    except Exception as e:
        result['status'] = 'ERROR'
        result['error'] = str(e)
    
    return result


def main():
    args = parse_args()
    
    # Initialize configuration
    try:
        config_manager.initialize(args.config)
        config._ensure_initialized()
        if args.verbose:
            print(f"Configuration loaded successfully")
            print(f"Email: {config.EMAIL_ADDRESS}")
            print(f"Provider: {args.provider}")
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)
    
    # Create PostOffice instance
    post = PostOffice(args.provider, {
        'email': config.EMAIL_ADDRESS,
        'password': config.PASSWORD
    })
    
    # Connect
    if args.verbose:
        print("\nConnecting...")
    
    try:
        post.connect()
        if args.verbose:
            print("Connected successfully")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)
    
    # List all folders if requested
    all_folders = []
    if args.list_all:
        all_folders = list_all_folders(post)
    
    # Determine which folders to test
    test_folders = []
    if args.folders:
        test_folders = args.folders
    else:
        # Use folders from config
        test_folders = [
            config.INBOX,
            config.SPAM_LEARN,
            config.HAM_LEARN,
            config.SPAM_FOLDER,
            config.HAM_FOLDER,
        ]
        # Remove duplicates and None values
        test_folders = [f for f in set(test_folders) if f]
    
    # Test each folder
    print("\n" + "="*60)
    print("Folder Test Results")
    print("="*60)
    
    results = []
    for folder in test_folders:
        result = test_folder(post, folder)
        results.append(result)
        
        # Display result with color coding
        if result['status'] == 'OK':
            print(f"  ✓ {result['folder']:<40} {result['count']:>6} messages")
        elif result['status'] == 'FAILED':
            print(f"  ✗ {result['folder']:<40} FAILED - {result['error']}")
        else:
            print(f"  ⚠ {result['folder']:<40} ERROR - {result['error']}")
    
    print("="*60)
    
    # Summary
    ok_count = sum(1 for r in results if r['status'] == 'OK')
    failed_count = sum(1 for r in results if r['status'] == 'FAILED')
    error_count = sum(1 for r in results if r['status'] == 'ERROR')
    
    print(f"\nSummary: {ok_count} OK, {failed_count} Failed, {error_count} Errors")
    
    # Cleanup
    post.close()
    if args.verbose:
        print("\nConnection closed.")


if __name__ == "__main__":
    main()