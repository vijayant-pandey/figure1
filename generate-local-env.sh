#!/usr/bin/env bash
set -Eeuo pipefail

SECRET_NAME="services-api-env"
OUT_FILE=".env.runtime"
IS_LOCAL_BUILD=false

ensure_jq() {
  if command -v jq >/dev/null 2>&1; then return; fi
    echo "jq not found; installing..." >&2
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y jq >/dev/null
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache jq >/dev/null
  elif command -v yum >/dev/null 2>&1; then
    yum install -y -q jq >/dev/null
  else
    echo "No known package manager available to install jq. Please install manually:" >&2
    echo "  Windows : winget install jqlang.jq   (or: choco install jq / scoop install jq)" >&2
    echo "  macOS   : brew install jq" >&2
    echo "  Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y jq" >&2
    exit 2
  fi
}

# Runtime path (inside container)
if [[ "${BUILD_ENV:-false}" == "true" ]]; then
  echo "Replaying environment from $OUT_FILE..."
  if [[ -f "$OUT_FILE" ]]; then
    while IFS= read -r LINE; do
      [[ -z "$LINE" || "$LINE" == \#* ]] && continue
      KEY="${LINE%%=*}"
      VALUE="${LINE#*=}"
      export "$KEY"="$VALUE"
      # echo "Exported $KEY=$VALUE"
    done < "$OUT_FILE"
    # clean up after exporting
    # keeping this here for discussion
    # but enabling this line will fail the env variables if server restarts.
    # keep it commented out for now
    # rm -f "$OUT_FILE"
  else
    echo "$OUT_FILE missing — cannot export vars."
  fi
  return 0
fi

# Local dev path (LOCAL_BUILD=true in .env)
if [[ -f ".env" && "$(grep -E '^LOCAL_BUILD=true$' .env || true)" == "LOCAL_BUILD=true" ]]; then
  IS_LOCAL_BUILD=true
fi

echo "LOCAL_BUILD=$IS_LOCAL_BUILD"

# Make sure jq is installed before parsing JSON
ensure_jq
# Generate .env.runtime file (Cloud Build / local build)
echo "# Generated $(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "$OUT_FILE"

gcloud secrets versions access latest --secret="$SECRET_NAME" | jq -r 'to_entries | sort_by(.key)[] | "\(.key)=\(.value | @json)"' | while IFS='=' read -r KEY LINE; do

#  LINE="${LINE%$'\r'}"

  if $IS_LOCAL_BUILD; then
    case "$KEY" in
      "DB_HOST"*) LINE="host.docker.internal" ;;
      "REDIS_URL"*) LINE="redis://host.docker.internal:6379" ;;
      "CELERY_BROKER_URL"*) LINE="redis://host.docker.internal:6379" ;;
    esac
  fi
  # stringify & escape value for .env (double-quoted)

  CLEAN_VAL="$(echo "$LINE" | sed -e 's/^"//' -e 's/"$//')"
  printf '%s=%s\n' "$KEY" "$CLEAN_VAL" >> "$OUT_FILE"
done

echo "$OUT_FILE generated successfully."
