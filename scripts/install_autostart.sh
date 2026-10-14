#!/bin/zsh
# Keep the gold trade filter + Telegram bot running 24/7 (macOS LaunchAgent):
#  - starts at login, restarts automatically if it ever crashes (KeepAlive)
#  - wrapped in `caffeinate -s` so the Mac does not sleep while it is plugged in
#    (a MacBook with the lid closed and no external display will still sleep)
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/com.gold.tradefilter.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/data"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gold.tradefilter</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/caffeinate</string><string>-s</string>
    <string>$PY</string><string>-m</string><string>uvicorn</string><string>server.app:app</string>
    <string>--host</string><string>127.0.0.1</string><string>--port</string><string>8787</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DIR/data/server.log</string>
  <key>StandardErrorPath</key><string>$DIR/data/server.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed. Dashboard: http://localhost:8787  (log: $DIR/data/server.log)"
echo "Stop/uninstall: launchctl unload $PLIST && rm $PLIST"
