#!/usr/bin/env bash
# Launch the Azure Cost & Governance Dashboard in demo mode.
set -e
cd "$(dirname "$0")"

STREAMLIT_BIN="/Users/sid/Library/Python/3.9/bin/streamlit"
if [ ! -x "$STREAMLIT_BIN" ]; then
    STREAMLIT_BIN="$(command -v streamlit || true)"
fi
if [ -z "$STREAMLIT_BIN" ]; then
    echo "streamlit not found. Run: pip3 install -r requirements.txt" >&2
    exit 1
fi

export DEMO_MODE="${DEMO_MODE:-true}"
exec "$STREAMLIT_BIN" run app.py "$@"
