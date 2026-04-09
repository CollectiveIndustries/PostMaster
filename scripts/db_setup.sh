#!/usr/bin/env bash

echo "Setting up MariaDB for PostMaster..."

# Generate random password
DB_PASSWORD=$(openssl rand -base64 24)

# Create user and database
sudo mysql << EOF
CREATE USER IF NOT EXISTS 'postmaster_user'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
CREATE DATABASE IF NOT EXISTS postmaster_db;
GRANT ALL PRIVILEGES ON postmaster_db.* TO 'postmaster_user'@'localhost';
FLUSH PRIVILEGES;
EOF

echo "✓ Database user created"
echo "✓ Database 'postmaster_db' created"
echo ""
echo "Your database credentials:"
echo "  User: postmaster_user"
echo "  Password: $DB_PASSWORD"
echo "  Database: postmaster_db"
echo ""
echo "Add these to your .env file or configuration"

# Save to .env file
echo "POSTMASTER_DB_USER=postmaster_user" >> .env
echo "POSTMASTER_DB_PASSWORD=$DB_PASSWORD" >> .env
echo "POSTMASTER_DB_NAME=postmaster_db" >> .env
echo "POSTMASTER_DB_HOST=localhost" >> .env

echo "✓ Credentials saved to .env file"