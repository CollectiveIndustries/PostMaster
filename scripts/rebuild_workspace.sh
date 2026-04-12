# Create new virtual environment with Python 3.13
python3.13 -m venv .venv

# Activate it
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install from requirements.txt if it exists
pip install -r requirements.txt

# If requirements.txt doesn't have everything, install core dependencies:
pip install tensorflow
pip install beautifulsoup4
pip install pyyaml
pip install requests
pip install mysql-connector-python
pip install mariadb
pip install python-dotenv

# Install development dependencies
pip install black
pip install ruff
pip install mypy
pip install pre-commit
pip install pytest
pip install pylint
pip install flake8
pip install isort

# Install pre-commit hooks
pre-commit install

# Run pre-commit on all files to format them
pre-commit run --all-files

# Start MariaDB
sudo systemctl start mariadb
sudo systemctl enable mariadb

# Verify database exists
mysql -u postmaster_user -p -h localhost -e "SHOW DATABASES;" postmaster_db

# If database doesn't exist, create it
mysql -u root -p << 'EOF'
CREATE DATABASE IF NOT EXISTS postmaster_db;
GRANT ALL PRIVILEGES ON postmaster_db.* TO 'postmaster_user'@'localhost';
FLUSH PRIVILEGES;
EOF

# Run the SQL schema
mysql -u postmaster_user -p -h localhost postmaster_db < sql/install.sql

