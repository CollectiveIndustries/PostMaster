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
    
    def get_queue_stats(self) -> Dict:
        """Get detailed queue statistics using new processed column"""
        # Get pending emails (processed = 0)
        pending = self.run_query(
            "SELECT COUNT(*) FROM mail_que WHERE processed = 0;"
        )
        pending_count = int(pending[0][0]) if pending and pending[0] else 0
        
        # Get completed emails (processed = 1)
        completed = self.run_query(
            "SELECT COUNT(*) FROM mail_que WHERE processed = 1;"
        )
        completed_count = int(completed[0][0]) if completed and completed[0] else 0
        
        # Get total
        total = self.run_query("SELECT COUNT(*) FROM mail_que;")
        total_count = int(total[0][0]) if total and total[0] else 0
        
        return {
            'pending': pending_count,
            'completed': completed_count,
            'total': total_count
        }
    
    def get_processed_count(self) -> int:
        """Get number of processed emails from log"""
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
    
    def get_training_counts(self) -> Tuple[int, int, int, int]:
        """Get count of training emails (both pending and completed)"""
        # Get pending training emails (in queue, not processed)
        spam_pending = self.run_query(
            "SELECT COUNT(*) FROM mail_que WHERE thread_marker = 'Trainer-Spam' AND processed = 0;"
        )
        ham_pending = self.run_query(
            "SELECT COUNT(*) FROM mail_que WHERE thread_marker = 'Trainer-Ham' AND processed = 0;"
        )
        
        # Get completed training emails (already trained)
        spam_completed = self.run_query(
            "SELECT COUNT(*) FROM mail_que WHERE thread_marker = 'Trainer-Spam' AND processed = 1;"
        )
        ham_completed = self.run_query(
            "SELECT COUNT(*) FROM mail_que WHERE thread_marker = 'Trainer-Ham' AND processed = 1;"
        )
        
        spam_pending_count = int(spam_pending[0][0]) if spam_pending and spam_pending[0] else 0
        ham_pending_count = int(ham_pending[0][0]) if ham_pending and ham_pending[0] else 0
        spam_completed_count = int(spam_completed[0][0]) if spam_completed and spam_completed[0] else 0
        ham_completed_count = int(ham_completed[0][0]) if ham_completed and ham_completed[0] else 0
        
        return spam_pending_count, ham_pending_count, spam_completed_count, ham_completed_count
    
    def get_trained_model_stats(self) -> Dict:
        """Get statistics about trained emails from email_hashes"""
        trained = self.run_query(
            "SELECT COUNT(*) FROM email_hashes WHERE trained = 1;"
        )
        total_trained = int(trained[0][0]) if trained and trained[0] else 0
        
        # Get classification distribution of trained emails
        dist = self.run_query(
            "SELECT classification_id, COUNT(*) FROM email_hashes WHERE trained = 1 GROUP BY classification_id;"
        )
        trained_by_class = {}
        for row in dist:
            if len(row) >= 2:
                trained_by_class[row[0]] = int(row[1])
        
        return {
            'total_trained': total_trained,
            'by_class': trained_by_class
        }
    
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
        queue_stats = self.get_queue_stats()
        processed = self.get_processed_count()
        folder_dist = self.get_folder_distribution()
        spam_pending, ham_pending, spam_completed, ham_completed = self.get_training_counts()
        trained_stats = self.get_trained_model_stats()
        
        # Calculate totals
        total_queued = queue_stats['total']
        pending = queue_stats['pending']
        completed_queue = queue_stats['completed']
        
        # Header
        print(f"{Colors.BOLD}{Colors.WHITE}╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.WHITE}║{Colors.CYAN}                                    PostMaster Email Classification Dashboard - {self.get_timestamp()}{Colors.WHITE}                                                      ║{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.WHITE}╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝{Colors.NC}")
        print()
        
        # Panel 1: Queue Overview (updated with processed column)
        print(f"{Colors.BOLD}{Colors.BLUE}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.BLUE}│{Colors.WHITE} 📊 QUEUE STATUS{Colors.BLUE}                                                                                                                │{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.BLUE}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤{Colors.NC}")
        
        if total_queued > 0:
            pending_percent = int(pending * 100 / total_queued) if total_queued > 0 else 0
            completed_percent = int(completed_queue * 100 / total_queued) if total_queued > 0 else 0
            print(f"{Colors.BLUE}│{Colors.NC}  📨 {Colors.WHITE}Total Emails in Queue:{Colors.NC} {self.format_number(total_queued):>10}")
            print(f"{Colors.BLUE}│{Colors.NC}     {self.draw_bar(completed_percent, 50, Colors.GREEN)} {completed_percent}% Completed ({self.format_number(completed_queue)})")
            print(f"{Colors.BLUE}│{Colors.NC}     {self.draw_bar(pending_percent, 50, Colors.YELLOW)} {pending_percent}% Pending ({self.format_number(pending)})")
        else:
            print(f"{Colors.BLUE}│{Colors.NC}  📨 {Colors.WHITE}Queue:{Colors.NC} Empty - No emails to process")
        
        print(f"{Colors.BOLD}{Colors.BLUE}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘{Colors.NC}")
        print()
        
        # Panel 2: Training Status (updated with pending vs completed)
        print(f"{Colors.BOLD}{Colors.MAGENTA}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}│{Colors.WHITE} 🧠 TRAINING STATUS{Colors.MAGENTA}                                                                                                           │{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤{Colors.NC}")
        print(f"{Colors.MAGENTA}│{Colors.NC}  🚫 {Colors.WHITE}Spam Training:{Colors.NC}")
        print(f"{Colors.MAGENTA}│{Colors.NC}     Pending:  {self.format_number(spam_pending):>10} emails")
        print(f"{Colors.MAGENTA}│{Colors.NC}     Trained:  {self.format_number(spam_completed):>10} emails")
        print(f"{Colors.MAGENTA}│{Colors.NC}  ✅ {Colors.WHITE}Ham Training:{Colors.NC}")
        print(f"{Colors.MAGENTA}│{Colors.NC}     Pending:  {self.format_number(ham_pending):>10} emails")
        print(f"{Colors.MAGENTA}│{Colors.NC}     Trained:  {self.format_number(ham_completed):>10} emails")
        
        total_train_completed = spam_completed + ham_completed
        if total_train_completed > 0:
            print(f"{Colors.MAGENTA}│{Colors.NC}  📊 {Colors.WHITE}Total Trained:{Colors.NC} {self.format_number(total_train_completed)} emails")
        
        print(f"{Colors.BOLD}{Colors.MAGENTA}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘{Colors.NC}")
        print()
        
        # Panel 3: Model Statistics (new panel)
        print(f"{Colors.BOLD}{Colors.CYAN}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.CYAN}│{Colors.WHITE} 🤖 MODEL STATISTICS{Colors.CYAN}                                                                                                             │{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.CYAN}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤{Colors.NC}")
        print(f"{Colors.CYAN}│{Colors.NC}  🎓 {Colors.WHITE}Emails in Training Set:{Colors.NC} {self.format_number(trained_stats['total_trained']):>10}")
        
        if trained_stats['by_class']:
            spam_trained = trained_stats['by_class'].get('0', 0)
            ham_trained = trained_stats['by_class'].get('1', 0)
            print(f"{Colors.CYAN}│{Colors.NC}     Spam: {self.format_number(spam_trained):>10}")
            print(f"{Colors.CYAN}│{Colors.NC}     Ham:  {self.format_number(ham_trained):>10}")
        print(f"{Colors.BOLD}{Colors.CYAN}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘{Colors.NC}")
        print()
        
        # Panel 4: Folder Distribution
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
        
        # Panel 5: System Health
        print(f"{Colors.BOLD}{Colors.YELLOW}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.YELLOW}│{Colors.WHITE} 💚 SYSTEM HEALTH{Colors.YELLOW}                                                                                                               │{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.YELLOW}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤{Colors.NC}")
        
        # Check database connection
        test_query = self.run_query("SELECT 1")
        if test_query and test_query[0] and test_query[0][0] == '1':
            print(f"{Colors.YELLOW}│{Colors.NC}  🗄️  Database:        {Colors.GREEN}Connected ✓{Colors.NC}")
        else:
            print(f"{Colors.YELLOW}│{Colors.NC}  🗄️  Database:        {Colors.RED}Disconnected ✗{Colors.NC}")
        
        # Check mail_que table structure (check for processed column)
        has_processed = self.run_query("SHOW COLUMNS FROM mail_que LIKE 'processed'")
        if has_processed:
            print(f"{Colors.YELLOW}│{Colors.NC}  📋 mail_que:       {Colors.GREEN}Active (with processed tracking) ✓{Colors.NC}")
        else:
            print(f"{Colors.YELLOW}│{Colors.NC}  📋 mail_que:       {Colors.YELLOW}Active (legacy schema) ⚠{Colors.NC}")
        
        # Check processing log
        log_exists = self.run_query("SHOW TABLES LIKE 'email_processing_log'")
        if log_exists:
            log_count = self.run_query("SELECT COUNT(*) FROM email_processing_log")
            log_count_value = int(log_count[0][0]) if log_count and log_count[0] else 0
            print(f"{Colors.YELLOW}│{Colors.NC}  📝 Processing Log:  {Colors.GREEN}Active ({self.format_number(log_count_value)} records) ✓{Colors.NC}")
        else:
            print(f"{Colors.YELLOW}│{Colors.NC}  📝 Processing Log:  {Colors.RED}Missing ✗{Colors.NC}")
        
        # Check email_hashes table for trained column
        has_trained = self.run_query("SHOW COLUMNS FROM email_hashes LIKE 'trained'")
        if has_trained:
            trained_count = self.run_query("SELECT COUNT(*) FROM email_hashes WHERE trained = 1")
            trained_value = int(trained_count[0][0]) if trained_count and trained_count[0] else 0
            print(f"{Colors.YELLOW}│{Colors.NC}  🏷️  email_hashes:   {Colors.GREEN}Active ({self.format_number(trained_value)} trained) ✓{Colors.NC}")
        else:
            print(f"{Colors.YELLOW}│{Colors.NC}  🏷️  email_hashes:   {Colors.YELLOW}Active (legacy schema) ⚠{Colors.NC}")
        
        print(f"{Colors.BOLD}{Colors.YELLOW}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘{Colors.NC}")
        print()
        
        # Footer with instructions
        print(f"{Colors.GRAY}Press Ctrl+C to exit dashboard | Updates every {self.interval} seconds{Colors.NC}")
    
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