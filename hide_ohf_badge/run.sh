#!/usr/bin/env bash
set -e

TARGET="/usr/local/lib/python3.13/site-packages/hass_frontend/static/images/ohf-badge.svg"

echo "[Hide OHF Badge] Starting"

if [ ! -f "$TARGET" ]; then
  echo "[ERROR] ohf-badge.svg not found"
  exit 1
fi

# Backup once
if [ ! -f "$TARGET.bak" ]; then
  cp "$TARGET" "$TARGET.bak"
  echo "[OK] Backup created"
fi

# Replace SVG
cat << 'EOF' > "$TARGET"
<svg xmlns="http://www.w3.org/2000/svg" width="160" height="40" viewBox="0 0 160 40">
</svg>
EOF

echo "[DONE] OHF badge hidden"
