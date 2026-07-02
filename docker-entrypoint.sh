#!/bin/sh
set -e

# Run database creation/seeding once
echo "Initializing database..."
flask init-db

# Sync serial numbers from seed JSON (idempotent, safe to run every time)
echo "Syncing employee serial numbers..."
flask update-serials

# Execute the main container command (Gunicorn)
exec "$@"
