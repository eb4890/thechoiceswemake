#!/bin/bash

# --- Database Backup Script ---
# This script is intended to run on the HOST machine (outside the container).
# It connects to the database via the port mapped in docker-compose.yaml (defaults to 5433).

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Configuration
DB_USER="choices_user"
DB_NAME="choices_archive"
DB_HOST="localhost"
DB_PORT="5433"
DB_PASSWORD=${DB_PASSWORD:-"your_very_strong_password_here"}
BACKUP_DIR="./backups"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Timestamp for the filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_$TIMESTAMP.sql.gz"

echo "[$(date)] Starting backup of $DB_NAME..."

# Execute pg_dump and compress on the fly
# PGPASSWORD is used to avoid interactive prompt
if PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    echo "[$(date)] Backup successful: $BACKUP_FILE"
    
    # Prune backups older than 14 days
    find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +14 -delete
    echo "[$(date)] Old backups (14d+) pruned."
else
    echo "[$(date)] ERROR: Backup failed!" >&2
    exit 1
fi
