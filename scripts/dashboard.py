#!/usr/bin/env python3
"""
PostMaster Dashboard - Real-time monitoring panel for email classification
Displays database queue, processing progress, and folder distribution

Usage: python scripts/dashboard.py [--config CONFIG_PATH] [--interval SECONDS] [--once]
"""

import argparse
import os
import sys
import time
import subprocess
from datetime import datetime
from typing import Dict, List, Tuple
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config_manager import config_manager


# ANSI color codes
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    MAGENTA = '\033[0;35m'
    WHITE = '\033[1;37m'
    GRAY = '\033[0;90m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


class Dashboard:
    def __init__(self, config_path: str = None, interval: int = 5):
        """Initialize dashboard with configuration"""
        self.interval = interval
        self.db_config = None
        self._load_config(config_path)
    
    def _load_config(self, config_path: str = None):
        """Load database configuration from ConfigManager"""
        try:
            config_manager.initialize(config_path)
            db_section = config_manager.get_section('database')
            if not db_section:
                db_section = config_manager.get_section('MySQL')
            
            self.db_config = {
                'user': db_section.get('user', 'postmaster_user'),
                'password': db_section.get('password', ''),
                'host': db_section.get('host', 'localhost'),
                'database': db_section.get('database', 'postmaster_db'),
                'port': db_section.get('port', 3306)
            }
        except Exception as e:
            print(f"Error loading configuration: {e}")
            sys.exit(1)
    
    def run_query(self, query: str) -> List[Tuple]:
        """Execute MySQL query and return results"""
        try:
            cmd = [
                'mysql',
                '-u', self.db_config['user'],
                f'-p{self.db_config['password']}',
                '-h', self.db_config['host'],
                self.db_config['database'],
                '-e', query,
                '--batch',
                '--skip-column-names'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                rows = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        rows.append(tuple(line.split('\t')))
                return rows
            return []
        except Exception as e:
            return [('ERROR', str(e))]
    
    def get_queue_count(self) -> int:
        """Get number of emails in processing queue"""
        result = self.run_query("SELECT COUNT(*) FROM mail_que;")
        if result and result[0]:
            return int(result[0][0])
        return 0
    
    def get_processed_count(self) -> int:
        """Get number of processed emails"""
        result = self.run_query("SELECT COUNT(*) FROM email_processing_log;")
        if result and result[0]:
            return int(result[0][0])
        return 0
    
    def get_folder_distribution(self) -> Dict[str, int]:
        """Get distribution of emails across folders"""
        result = self.run_query(
            "SELECT destination_folder, COUNT(*) FROM email_processing_log "
            "GROUP BY destination_folder ORDER BY COUNT(*) DESC;"
        )
        distribution = {}
        for row in result:
            if len(row) >= 2:
                distribution[row[0]] = int(row[1])
        return distribution
    
    def get_training_counts(self) -> Tuple[int, int]:
        """Get count of spam and ham training emails"""
        spam = self.run_query(
            "SELECT COUNT(*) FROM mail_que WHERE thread_marker = 'Trainer-Spam';"
        )
        ham = self.run_query(
            "SELECT COUNT(*) FROM mail_que WHERE thread_marker = 'Trainer-Ham';"
        )
        spam_count = int(spam[0][0]) if spam and spam[0] else 0
        ham_count = int(ham[0][0]) if ham and ham[0] else 0
        return spam_count, ham_count
    
    def draw_bar(self, percent: int, width: int, color: str) -> str:
        """Draw a progress bar"""
        filled = int(percent * width / 100)
        empty = width - filled
        return f"{color}{'█' * filled}{Colors.GRAY}{'░' * empty}{Colors.NC}"
    
    def format_number(self, num: int) -> str:
        """Format large numbers with commas"""
        return f"{num:,}"
    
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name != 'nt' else 'cls')
    
    def get_timestamp(self) -> str:
        """Get current timestamp"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def display(self):
        """Display a single dashboard update"""
        # Get all metrics
        queued = self.get_queue_count()
        processed = self.get_processed_count()
        folder_dist = self.get_folder_distribution()
        spam_train, ham_train = self.get_training_counts()
        
        # Calculate total
        total = queued + processed
        
        # Header
        print(f"{Colors.BOLD}{Colors.WHITE}╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.WHITE}║{Colors.CYAN}                                    PostMaster Email Classification Dashboard - {self.get_timestamp()}{Colors.WHITE}                                                      ║{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.WHITE}╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝{Colors.NC}")
        print()
        
        # Panel 1: Overview
        print(f"{Colors.BOLD}{Colors.BLUE}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.BLUE}│{Colors.WHITE} 📊 OVERVIEW{Colors.BLUE}                                                                                                                   │{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.BLUE}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤{Colors.NC}")
        
        if total > 0:
            queue_percent = int(queued * 100 / total)
            processed_percent = int(processed * 100 / total)
            print(f"{Colors.BLUE}│{Colors.NC}  📨 {Colors.WHITE}Total Emails:{Colors.NC} {self.format_number(total):>10}")
            print(f"{Colors.BLUE}│{Colors.NC}     {self.draw_bar(processed_percent, 50, Colors.GREEN)} {processed_percent}% Processed ({self.format_number(processed)})")
            print(f"{Colors.BLUE}│{Colors.NC}     {self.draw_bar(queue_percent, 50, Colors.YELLOW)} {queue_percent}% Queued ({self.format_number(queued)})")
        else:
            print(f"{Colors.BLUE}│{Colors.NC}  📨 {Colors.WHITE}Total Emails:{Colors.NC} {self.format_number(total):>10}")
            print(f"{Colors.BLUE}│{Colors.NC}     {Colors.GRAY}No data yet{Colors.NC}")
        
        print(f"{Colors.BOLD}{Colors.BLUE}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘{Colors.NC}")
        print()
        
        # Panel 2: Training Status
        print(f"{Colors.BOLD}{Colors.MAGENTA}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}│{Colors.WHITE} 🧠 TRAINING STATUS{Colors.MAGENTA}                                                                                                           │{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤{Colors.NC}")
        print(f"{Colors.MAGENTA}│{Colors.NC}  🚫 {Colors.WHITE}Spam Training:{Colors.NC} {self.format_number(spam_train):>10} emails")
        print(f"{Colors.MAGENTA}│{Colors.NC}  ✅ {Colors.WHITE}Ham Training:{Colors.NC}  {self.format_number(ham_train):>10} emails")
        
        total_train = spam_train + ham_train
        if total_train > 0:
            train_percent = min(100, int(total_train * 100 / 500))
            print(f"{Colors.MAGENTA}│{Colors.NC}     {self.draw_bar(train_percent, 50, Colors.CYAN)} {train_percent}% of target (500 emails)")
        print(f"{Colors.BOLD}{Colors.MAGENTA}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘{Colors.NC}")
        print()
        
        # Panel 3: Folder Distribution
        print(f"{Colors.BOLD}{Colors.GREEN}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.GREEN}│{Colors.WHITE} 📁 FOLDER DISTRIBUTION{Colors.GREEN}                                                                                                         │{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.GREEN}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤{Colors.NC}")
        
        if folder_dist:
            max_count = max(folder_dist.values()) if folder_dist else 1
            for folder, count in sorted(folder_dist.items(), key=lambda x: x[1], reverse=True)[:10]:
                display_name = folder[:35] + "..." if len(folder) > 35 else folder
                bar_width = int(count * 40 / max_count) if max_count > 0 else 0
                bar = f"{Colors.GREEN}{'█' * bar_width}{Colors.NC}"
                print(f"{Colors.GREEN}│{Colors.NC}  {display_name:<38} {bar} {self.format_number(count):>8}")
        else:
            print(f"{Colors.GREEN}│{Colors.NC}  {Colors.GRAY}No processed emails yet{Colors.NC}")
        
        print(f"{Colors.BOLD}{Colors.GREEN}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘{Colors.NC}")
        print()
        
        # Panel 4: System Health
        print(f"{Colors.BOLD}{Colors.YELLOW}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.YELLOW}│{Colors.WHITE} 💚 SYSTEM HEALTH{Colors.YELLOW}                                                                                                               │{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.YELLOW}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤{Colors.NC}")
        
        test_query = self.run_query("SELECT 1")
        if test_query and test_query[0] and test_query[0][0] == '1':
            print(f"{Colors.YELLOW}│{Colors.NC}  🗄️  Database:     {Colors.GREEN}Connected ✓{Colors.NC}")
        else:
            print(f"{Colors.YELLOW}│{Colors.NC}  🗄️  Database:     {Colors.RED}Disconnected ✗{Colors.NC}")
        
        mail_que_exists = self.run_query("SHOW TABLES LIKE 'mail_que'")
        if mail_que_exists:
            print(f"{Colors.YELLOW}│{Colors.NC}  📋 mail_que:     {Colors.GREEN}Active ✓{Colors.NC}")
        else:
            print(f"{Colors.YELLOW}│{Colors.NC}  📋 mail_que:     {Colors.RED}Missing ✗{Colors.NC}")
        
        log_exists = self.run_query("SHOW TABLES LIKE 'email_processing_log'")
        if log_exists:
            print(f"{Colors.YELLOW}│{Colors.NC}  📝 Processing Log: {Colors.GREEN}Active ✓{Colors.NC}")
        else:
            print(f"{Colors.YELLOW}│{Colors.NC}  📝 Processing Log: {Colors.RED}Missing ✗{Colors.NC}")
        
        print(f"{Colors.BOLD}{Colors.YELLOW}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘{Colors.NC}")
        print()
    
    def run(self, once: bool = False):
        """Run the dashboard"""
        if once:
            self.clear_screen()
            self.display()
        else:
            try:
                while True:
                    self.clear_screen()
                    self.display()
                    print(f"{Colors.GRAY}Press Ctrl+C to exit dashboard | Updates every {self.interval} seconds{Colors.NC}")
                    time.sleep(self.interval)
            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}Dashboard stopped.{Colors.NC}")
                sys.exit(0)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='PostMaster Dashboard - Real-time monitoring panel',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                              # Run dashboard with 5 second updates
    %(prog)s --interval 10                # Update every 10 seconds
    %(prog)s --once                       # Show single snapshot and exit
    %(prog)s --config /path/to/config.yaml
        """
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to configuration YAML file'
    )
    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=5,
        help='Update interval in seconds (default: 5)'
    )
    parser.add_argument(
        '--once', '-o',
        action='store_true',
        help='Run once and exit (single snapshot)'
    )
    return parser.parse_args()


def main():
    args = parse_args()
    dashboard = Dashboard(config_path=args.config, interval=args.interval)
    dashboard.run(once=args.once)


if __name__ == "__main__":
    main()