#!/bin/bash
set -e

echo "Restoring database from dump..."
pg_restore \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v --no-owner --no-acl --clean --if-exists \
  /docker-entrypoint-initdb.d/dump.dump

echo "Database restore completed!"