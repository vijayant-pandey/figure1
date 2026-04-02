#!/usr/bin/env bash
set -e

echo "Creating environment variables..."
# source ensures exports persist in this shell
# disabling this for now. This will be used for application level env variables but not need it atm.
# source ./generate-local-env.sh

# echo "Dumping critical environment variables..."
# printenv | sort | grep -E 'REDIS|DB|SECRET|URL' || true

echo "Starting Flask server..."
exec gunicorn figure1.run.flask_startup:app --bind 0.0.0.0:30000