#!/usr/bin/env bash
# Finance News Feed – one-time setup
# Installs feedparser, runs the feed once, then schedules it daily at 7 AM.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON=$(command -v python3 || { echo "python3 not found. Install it from python.org"; exit 1; })
PLIST_LABEL="com.$(whoami).financenews"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
LOG_DIR="$DIR/logs"

echo ""
echo "  Finance News Feed – Setup"
echo "  ────────────────────────"
echo ""

# 1. Install feedparser
echo "→ Installing feedparser..."
"$PYTHON" -m pip install feedparser --quiet --break-system-packages 2>/dev/null \
  || "$PYTHON" -m pip install feedparser --quiet --user 2>/dev/null \
  || "$PYTHON" -m pip install feedparser --quiet
echo "  ✓ feedparser ready"

# 2. Ensure directories exist
mkdir -p "$DIR/output" "$LOG_DIR"

# 3. First run
echo ""
echo "→ Fetching news now..."
"$PYTHON" "$DIR/finance_news.py"

# 4. Open the page
open "$DIR/output/index.html"

# 5. Write launchd plist for daily 7 AM
echo "→ Scheduling daily run at 7:00 AM..."
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${DIR}/finance_news.py</string>
  </array>

  <!-- Run daily at 7:00 AM -->
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>   <integer>7</integer>
    <key>Minute</key> <integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/err.log</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>

  <!-- Catch up if Mac was asleep at run time -->
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST

# 6. Load the agent
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load -w "$PLIST_PATH"
echo "  ✓ Scheduled"

echo ""
echo "  ✅  All done!"
echo ""
echo "  News page : $DIR/output/index.html"
echo "  Runs daily: 7:00 AM (launchd)"
echo ""
echo "  To run manually:"
echo "    python3 \"$DIR/finance_news.py\" && open \"$DIR/output/index.html\""
echo ""
echo "  To unschedule:"
echo "    launchctl unload \"$PLIST_PATH\" && rm \"$PLIST_PATH\""
echo ""
