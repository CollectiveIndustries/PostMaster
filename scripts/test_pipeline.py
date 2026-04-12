#!/usr/bin/env python3
"""
Test the complete email pipeline including IMAP connection and folder access
Usage: python scripts/test_pipeline.py [--config CONFIG_PATH] [--provider PROVIDER] [--verbose]
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
        description='Test the complete email pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                                    # Test with default config
    %(prog)s --config /opt/config.d/config.yaml
    %(prog)s --provider outlook                 # Test Outlook instead of Gmail
    %(prog)s --verbose                          # Show detailed output
    %(prog)s --test-folders                     # Test all configured folders
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
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--test-folders', '-f',
        action='store_true',
        help='Test all configured folders (INBOX, SPAM_LEARN, HAM_LEARN, etc.)'
    )
    return parser.parse_args()


def test_connection(post: PostOffice, verbose: bool = False) -> bool:
    """Test the IMAP connection"""
    if verbose:
        print("\n" + "-"*40)
        print("Testing Connection")
        print("-"*40)
    
    try:
        post.connect()
        if verbose:
            print("  ✓ Connection successful")
            print(f"  ✓ Provider: {type(post.provider).__name__}")
        
        # Test IMAP connection with a NOOP command
        if hasattr(post.provider, 'imap_conn') and post.provider.imap_conn:
            post.provider.imap_conn.noop()
            if verbose:
                print("  ✓ IMAP connection alive")
        return True
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return False


def test_folder_access(post: PostOffice, folder: str, verbose: bool = False) -> dict:
    """Test access to a specific folder"""
    result = {'folder': folder, 'success': False, 'count': 0, 'error': None}
    
    if verbose:
        print(f"\n  Testing folder: {folder}")
    
    try:
        total = post.total_emails(folder)
        result['success'] = True
        result['count'] = total
        if verbose:
            print(f"    ✓ Access successful")
            print(f"    ✓ Messages: {total}")
    except Exception as e:
        result['error'] = str(e)
        if verbose:
            print(f"    ✗ Access failed: {e}")
    
    return result


def test_message_fetch(post: PostOffice, folder: str, limit: int = 5, verbose: bool = False) -> bool:
    """Test fetching messages from a folder"""
    if verbose:
        print(f"\n  Testing message fetch from: {folder}")
    
    try:
        if hasattr(post.provider, 'fetch_messages'):
            messages = post.provider.fetch_messages(folder, limit=limit)
            if messages:
                if verbose:
                    print(f"    ✓ Successfully fetched {len(messages)} messages")
                    for i, msg in enumerate(messages[:3]):
                        print(f"      Message {i+1}: {len(msg)} bytes")
                return True
            else:
                if verbose:
                    print(f"    ⚠ No messages found (folder may be empty)")
                return True  # Not an error, just empty
        else:
            if verbose:
                print(f"    ⚠ fetch_messages not implemented for this provider")
            return False
    except Exception as e:
        if verbose:
            print(f"    ✗ Failed to fetch messages: {e}")
        return False


def main():
    args = parse_args()
    
    print("="*60)
    print("PostMaster Pipeline Test")
    print("="*60)
    
    # Initialize configuration
    try:
        config_manager.initialize(args.config)
        config._ensure_initialized()
        print(f"\n✓ Configuration loaded")
        if args.verbose:
            print(f"  Email: {config.EMAIL_ADDRESS}")
            print(f"  IMAP Server: {config.IMAP_URL}:{config.IMAP_PORT}")
            print(f"  Provider: {args.provider}")
    except Exception as e:
        print(f"\n✗ Failed to load configuration: {e}")
        sys.exit(1)
    
    # Create PostOffice instance
    post = PostOffice(args.provider, {
        'email': config.EMAIL_ADDRESS,
        'password': config.PASSWORD
    })
    
    # Test 1: Connection
    print("\n" + "="*40)
    print("TEST 1: IMAP Connection")
    print("="*40)
    
    if not test_connection(post, args.verbose):
        print("\n✗ Pipeline test FAILED - Cannot connect to IMAP server")
        sys.exit(1)
    
    # Determine folders to test
    if args.test_folders:
        folders_to_test = [
            ('INBOX', config.INBOX),
            ('Spam Learn', config.SPAM_LEARN),
            ('Ham Learn', config.HAM_LEARN),
            ('Spam Folder', config.SPAM_FOLDER),
            ('Ham Folder', config.HAM_FOLDER),
        ]
        # Remove None values
        folders_to_test = [(name, path) for name, path in folders_to_test if path]
    else:
        folders_to_test = [
            ('INBOX', config.INBOX),
            ('Spam Learn', config.SPAM_LEARN),
            ('Ham Learn', config.HAM_LEARN),
        ]
    
    # Test 2: Folder Access
    print("\n" + "="*40)
    print("TEST 2: Folder Access")
    print("="*40)
    
    folder_results = []
    for display_name, folder_path in folders_to_test:
        print(f"\n  📁 {display_name}: {folder_path}")
        result = test_folder_access(post, folder_path, args.verbose)
        folder_results.append(result)
    
    # Test 3: Message Fetch (only on folders with messages)
    print("\n" + "="*40)
    print("TEST 3: Message Fetch")
    print("="*40)
    
    for result in folder_results:
        if result['success'] and result['count'] > 0:
            print(f"\n  📧 Fetching from: {result['folder']}")
            test_message_fetch(post, result['folder'], limit=3, verbose=args.verbose)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    success_count = sum(1 for r in folder_results if r['success'])
    total_count = len(folder_results)
    
    print(f"\n  Folder Access: {success_count}/{total_count} successful")
    
    for result in folder_results:
        status = "✓" if result['success'] else "✗"
        count_info = f"({result['count']} messages)" if result['success'] else f"({result['error']})"
        print(f"    {status} {result['folder']:<35} {count_info}")
    
    # Final verdict
    print("\n" + "="*60)
    if success_count > 0:
        print("✓ Pipeline test PASSED - Core functionality working")
        if success_count < total_count:
            print("⚠ Some folders are inaccessible - Check folder paths in config")
    else:
        print("✗ Pipeline test FAILED - Cannot access any folders")
        print("  Check your IMAP connection and folder paths")
    print("="*60)
    
    # Cleanup
    post.close()
    if args.verbose:
        print("\nConnection closed.")


if __name__ == "__main__":
    main()