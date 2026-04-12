#!/usr/bin/env python3
"""
Setup proper permissions for the model directory used by PostMaster.
Loads configuration from the same config system as the main application.

Usage: python scripts/setup_model_dir.py [--config CONFIG_PATH] [--verbose]
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config_manager import config_manager
from lib.config import config


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Setup model directory permissions for PostMaster',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                              # Use default config
    %(prog)s --config /opt/config.d/config.yaml
    %(prog)s --verbose                    # Show detailed output
    %(prog)s --dry-run                    # Show what would be done without executing
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
        help='Enable verbose output'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force recreation of directory (backup existing files)'
    )
    return parser.parse_args()


def run_command(cmd: list, dry_run: bool = False, verbose: bool = False) -> bool:
    """Run a shell command with sudo"""
    if dry_run:
        print(f"  [DRY RUN] Would run: {' '.join(cmd)}")
        return True
    
    if verbose:
        print(f"  Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if result.stderr:
                print(f"  Error: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"  Exception: {e}")
        return False


def main():
    args = parse_args()
    
    print("=" * 60)
    print("PostMaster Model Directory Setup")
    print("=" * 60)
    
    # Initialize configuration
    try:
        config_manager.initialize(args.config)
        config._ensure_initialized()
        model_dir = config.TRAINING_DATA_PATH
        if args.verbose:
            print(f"\n✓ Configuration loaded")
            print(f"  Email: {config.EMAIL_ADDRESS}")
            print(f"  Model Directory: {model_dir}")
    except Exception as e:
        print(f"\n✗ Failed to load configuration: {e}")
        sys.exit(1)
    
    print(f"\n📁 Model Directory: {model_dir}")
    
    # Check if directory exists and has content
    model_path = Path(model_dir)
    if model_path.exists():
        files = list(model_path.glob('*'))
        if files:
            print(f"  Existing files: {len(files)}")
            if args.verbose:
                for f in files:
                    print(f"    - {f.name}")
            
            if args.force:
                # Backup existing directory
                backup_dir = model_path.parent / f"{model_path.name}_backup_{int(time.time())}"
                print(f"\n⚠ Force mode enabled. Backing up to: {backup_dir}")
                if not args.dry_run:
                    model_path.rename(backup_dir)
                    print(f"  ✓ Backed up existing directory")
            else:
                print(f"\n  Directory already exists with {len(files)} files.")
                print("  Use --force to backup and recreate, or run without --force to keep existing.")
    else:
        print(f"  Directory does not exist - will create")
    
    # Create directory
    print(f"\n🔧 Creating directory...")
    cmd = ['sudo', 'mkdir', '-p', model_dir]
    if not run_command(cmd, args.dry_run, args.verbose):
        print("✗ Failed to create directory")
        sys.exit(1)
    
    # Set ownership to current user
    print(f"\n👤 Setting ownership to {os.environ.get('USER', 'current user')}...")
    cmd = ['sudo', 'chown', '-R', f"{os.environ.get('USER', 'user')}:{os.environ.get('USER', 'user')}", model_dir]
    if not run_command(cmd, args.dry_run, args.verbose):
        print("✗ Failed to set ownership")
        sys.exit(1)
    
    # Set directory permissions (755)
    print(f"\n🔐 Setting directory permissions (755)...")
    cmd = ['sudo', 'chmod', '755', model_dir]
    if not run_command(cmd, args.dry_run, args.verbose):
        print("✗ Failed to set directory permissions")
        sys.exit(1)
    
    # Set file permissions (644) if files exist
    if model_path.exists() and list(model_path.glob('*')):
        print(f"\n📄 Setting file permissions (644)...")
        cmd = ['sudo', 'chmod', '-R', '644', f"{model_dir}/*"]
        if not run_command(cmd, args.dry_run, args.verbose):
            print("⚠ Failed to set some file permissions (may be fine if no files exist)")
    
    # Verify the setup
    print(f"\n✅ Verifying setup...")
    if args.dry_run:
        print("  [DRY RUN] Verification skipped")
    else:
        # Check directory exists
        if os.path.exists(model_dir):
            print(f"  ✓ Directory exists: {model_dir}")
            
            # Check permissions
            stat_info = os.stat(model_dir)
            perms = oct(stat_info.st_mode)[-3:]
            print(f"  ✓ Permissions: {perms}")
            
            # Check ownership
            owner = stat_info.st_uid
            print(f"  ✓ Owner UID: {owner}")
            
            # List contents
            contents = list(model_path.glob('*'))
            if contents:
                print(f"  ✓ Contents: {len(contents)} files")
                if args.verbose:
                    for f in contents[:10]:
                        print(f"    - {f.name}")
                    if len(contents) > 10:
                        print(f"    ... and {len(contents) - 10} more")
            else:
                print(f"  ✓ Directory is empty (ready for new files)")
        else:
            print(f"  ✗ Directory not found after creation!")
            sys.exit(1)
    
    # Summary
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print(f"\nModel directory: {model_dir}")
    print(f"Configuration source: {args.config or 'default (from ConfigManager)'}")
    
    if args.dry_run:
        print("\n⚠ This was a DRY RUN. No changes were made.")
        print("  Run without --dry-run to apply changes.")
    
    print("\nYou can now run PostMaster normally.")
    print("The model will be saved to this directory automatically.")


if __name__ == "__main__":
    import time
    main()