#!/usr/bin/env bash
set -Eeuo pipefail

# Secure Docker Compose wrapper that loads secrets from GCP Secret Manager
# This ensures no secrets are written to disk - all secrets stay in RAM only
# Secrets are loaded from services-api-env in GCP Secret Manager (JSON format)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# services-api-env is in JSON format
SECRET_NAME="services-api-env"

# Check if the command needs secrets to be loaded
needs_secrets() {
  local cmd="${1:-}"

  # Commands that need secrets (containers will be running/starting)
  case "$cmd" in
    up|run|exec|restart|start|create)
      return 0  # true - needs secrets
      ;;
    *)
      return 1  # false - doesn't need secrets
      ;;
  esac
}

ensure_gcloud() {
  if ! command -v gcloud >/dev/null 2>&1; then
    echo "❌ gcloud CLI not found. Please install it:" >&2
    echo "   https://cloud.google.com/sdk/docs/install" >&2
    exit 1
  fi
}

ensure_jq() {
  if command -v jq >/dev/null 2>&1; then
    return
  fi

  echo "❌ jq not found. Please install it:" >&2
  echo "   macOS   : brew install jq" >&2
  echo "   Debian/Ubuntu: sudo apt-get install -y jq" >&2
  echo "   Windows : winget install jqlang.jq" >&2
  exit 1
}

# Check if we need to load secrets for this command
if ! needs_secrets "${1:-}"; then
  echo "🐳 Running Docker Compose command (secrets not required)..."
  docker compose \
    -f "$SCRIPT_DIR/docker-compose.local.yaml" \
    "$@"
  exit 0
fi

echo "🔐 Loading secrets from GCP Secret Manager (${SECRET_NAME})..."
ensure_gcloud
ensure_jq

# Fetch secrets from GCP Secret Manager
# Temporarily disable pipefail to capture both output and exit code
set +e
SECRET_DATA=$(gcloud secrets versions access latest --secret="$SECRET_NAME" 2>&1)
GCLOUD_EXIT_CODE=$?
set -e

# Check if gcloud command failed
if [ $GCLOUD_EXIT_CODE -ne 0 ]; then
  echo "❌ Failed to fetch secrets from GCP Secret Manager" >&2
  echo "" >&2
  echo "Error output:" >&2
  echo "$SECRET_DATA" >&2
  echo "" >&2

  # Check for common error scenarios and provide helpful guidance
  if echo "$SECRET_DATA" | grep -qi "reauthentication required\|gcloud auth login"; then
    echo "🔑 Authentication required. Please run:" >&2
    echo "   gcloud auth login" >&2
  elif echo "$SECRET_DATA" | grep -qi "permission denied\|forbidden"; then
    echo "🔒 Permission denied. Please ensure you have access to the secret:" >&2
    echo "   Secret: $SECRET_NAME" >&2
  elif echo "$SECRET_DATA" | grep -qi "not found"; then
    echo "🔍 Secret not found. Please verify the secret exists:" >&2
    echo "   Secret: $SECRET_NAME" >&2
    echo "   Project: $(gcloud config get-value project 2>/dev/null || echo 'not set')" >&2
  fi

  exit 1
fi

if [ -z "$SECRET_DATA" ]; then
  echo "❌ Failed to fetch secrets from GCP Secret Manager: Empty response" >&2
  exit 1
fi

# Parse JSON format and export as environment variables (in-memory)
# Convert JSON object to KEY=VALUE pairs and export them
VAR_COUNT=0

# Use @json to properly escape values, then clean quotes
while IFS='=' read -r KEY LINE; do
  # Skip empty lines
  [[ -z "$KEY" ]] && continue

  # Remove surrounding quotes from JSON-escaped value
  VALUE="$(echo "$LINE" | sed -e 's/^"//' -e 's/"$//')"

  # Export to environment
  export "$KEY=$VALUE"
  VAR_COUNT=$((VAR_COUNT + 1))

done < <(echo "$SECRET_DATA" | jq -r 'to_entries | sort_by(.key)[] | "\(.key)=\(.value | @json)"')

echo "✅ Secrets loaded into environment (RAM only - not written to disk)"
echo "📦 Loaded $VAR_COUNT environment variables"

# Run docker compose with the local development configuration
echo "🐳 Running Docker Compose with in-memory secrets..."
echo ""

# Use the local development docker-compose file
docker compose \
  -f "$SCRIPT_DIR/docker-compose.local.yaml" \
  "$@"
