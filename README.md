# MailFilter

MailFilter is a lightweight Python application that connects to an IMAP server and applies configurable filtering rules on incoming emails. It supports actions like deleting messages, moving them to specific folders, or leaving them untouched.

## Features
- Configurable IMAP connection
- YAML-based filter rules
- Actions: delete, move to folder, mark as read
- Extendable architecture

## Requirements
- Python 3.8+
- `requests`
- `pyyaml`

## Installation
```bash
git clone <repo-url> mailfilter
cd mailfilter
python3 -m venv .venv
source .venv/bin/activate
pip install requests pyyaml
```