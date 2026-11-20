#!/usr/bin/env bash
# Sends a sample order to the n8n intake webhook and prints the result.
# Usage: ./scripts/send-sample.sh samples/01-email-clean.json
set -euo pipefail

FILE="${1:-samples/01-email-clean.json}"
URL="${2:-http://localhost:5678/webhook/order-intake}"
TOMORROW="$(date -d tomorrow +%F 2>/dev/null || date -v+1d +%F)"

sed "s/{{TOMORROW}}/${TOMORROW}/g" "$FILE" |
  curl -sS -X POST "$URL" -H "Content-Type: application/json" --data-binary @- |
  python3 -m json.tool
