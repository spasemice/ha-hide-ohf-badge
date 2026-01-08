#!/usr/bin/env bash
set -e

echo "[Hide OHF Badge] Starting"

# Dynamically find the Python site-packages directory
# Try common Python versions (3.9, 3.10, 3.11, 3.12, 3.13, 3.14)
TARGET=""
for PYTHON_VERSION in 3.14 3.13 3.12 3.11 3.10 3.9; do
  POSSIBLE_PATH="/usr/local/lib/python${PYTHON_VERSION}/site-packages/hass_frontend/static/images/ohf-badge.svg"
  if [ -f "$POSSIBLE_PATH" ]; then
    TARGET="$POSSIBLE_PATH"
    echo "[INFO] Found badge at: $TARGET"
    break
  fi
done

# If not found, try to find it using find command
if [ -z "$TARGET" ]; then
  echo "[INFO] Searching for ohf-badge.svg..."
  TARGET=$(find /usr/local/lib -name "ohf-badge.svg" -path "*/hass_frontend/static/images/*" 2>/dev/null | head -n 1)
  
  if [ -z "$TARGET" ]; then
    echo "[ERROR] ohf-badge.svg not found in expected locations"
    echo "[ERROR] Please ensure Home Assistant is installed and running"
    exit 1
  fi
  
  echo "[INFO] Found badge at: $TARGET"
fi

# Verify the file exists
if [ ! -f "$TARGET" ]; then
  echo "[ERROR] ohf-badge.svg not found at: $TARGET"
  exit 1
fi

# Backup once
if [ ! -f "$TARGET.bak" ]; then
  cp "$TARGET" "$TARGET.bak"
  echo "[OK] Backup created at: $TARGET.bak"
fi

# Replace SVG with empty one
cat << 'EOF' > "$TARGET"
<svg xmlns="http://www.w3.org/2000/svg" width="160" height="40" viewBox="0 0 160 40">
</svg>
EOF

echo "[DONE] OHF badge hidden successfully"
